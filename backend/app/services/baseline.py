"""Shared "lock the project's current schedule as a baseline" logic.

Used by three callers: the manual `POST /projects/{id}/evm/baseline` action
(app/api/routes/evm.py, company_admin-gated), the Program Library page's
automatic lock-on-first-import (app/services/xer_import.py, system-triggered,
no role gate), and the Baselines page's `POST /projects/{id}/evm/baseline/
program` upload — which locks on first use and calls `overwrite_active_baseline`
on every later replacement (the owner chose overwrite-in-place: no new baseline
version). See app/models/baseline.py for the "Vance Baseline Mandate" (at most
one `active` baseline per project).

Does not commit — callers own the transaction boundary.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.engine.evm.scurve_engine import generate_pv_curve
from app.models.activity import Activity
from app.models.baseline import (
    Baseline,
    BaselineActivity,
    BaselinePvCurve,
    BaselineResource,
    BaselineResourceAssignment,
    BaselineStatus,
)
from app.models.evm_snapshot import EvmSnapshot
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_import import ScheduleImport


class BaselineLockError(ValueError):
    """Base class for a schedule state that can't be locked as a baseline."""


class BaselineValidationError(BaselineLockError):
    """The schedule itself isn't lockable yet (no BAC, no planned dates)."""


class BaselineConflictError(BaselineLockError):
    """An active baseline or the requested version label already exists."""


def _compute_baseline_scope(
    activities: list[Activity],
) -> tuple[list[Activity], float, date, date]:
    """Duration-loaded activities + BAC + target start/end. Raises
    BaselineValidationError if the schedule isn't lockable yet."""
    eligible = [a for a in activities if (a.target_duration_hours or 0) > 0]

    bac = sum(a.target_duration_hours or 0.0 for a in eligible)
    if bac <= 0:
        raise BaselineValidationError(
            "Snapshot has no duration-loaded activities (BAC = 0). Ensure activities have a target duration."
        )

    starts = [s for s in (a.planned_start or a.early_start for a in eligible) if s]
    ends = [e for e in (a.planned_finish or a.early_finish for a in eligible) if e]
    if not starts or not ends:
        raise BaselineValidationError("Activities have no planned dates. Run CPM (import a scheduled .xer) first.")
    return eligible, round(bac, 4), min(starts), max(ends)


def _populate_baseline_children(
    db: Session, tenant_id: uuid.UUID, baseline_id: uuid.UUID, eligible: list[Activity], bac: float
) -> None:
    """Write the BaselineActivity rows + the linear PV curve for a baseline."""
    curve_input = []
    for a in eligible:
        a_start = a.planned_start or a.early_start
        a_end = a.planned_finish or a.early_finish
        db.add(
            BaselineActivity(
                id=uuid.uuid4(), tenant_id=tenant_id, baseline_id=baseline_id, activity_id=a.id,
                planned_manhours=a.target_duration_hours or 0.0, baseline_start=a_start, baseline_end=a_end,
                wbs_code=a.wbs_path,
            )
        )
        curve_input.append(
            {"planned_manhours": a.target_duration_hours or 0.0, "baseline_start": a_start, "baseline_end": a_end}
        )

    for curve_date, pv_daily, pv_cumulative in generate_pv_curve(curve_input, bac):
        db.add(
            BaselinePvCurve(
                id=uuid.uuid4(), tenant_id=tenant_id, baseline_id=baseline_id,
                curve_date=curve_date, pv_daily=pv_daily, pv_cumulative=pv_cumulative,
            )
        )


def _snapshot_baseline_resources(
    db: Session, tenant_id: uuid.UUID, baseline_id: uuid.UUID, project_id: uuid.UUID
) -> None:
    """Freeze the project's live P6 resources + budget lines against this
    baseline. The live `resources`/`resource_assignments` rows were just
    written by the same import_xer run; later update-programme imports replace
    them wholesale, so this copy is what keeps "the resources in the BSL"
    stable. See app/models/baseline.py."""
    resources = db.query(Resource).filter(Resource.project_id == project_id).all()
    rsrc_row_id_to_baseline_rsrc_id: dict[uuid.UUID, uuid.UUID] = {}
    for r in resources:
        br_id = uuid.uuid4()
        rsrc_row_id_to_baseline_rsrc_id[r.id] = br_id
        db.add(
            BaselineResource(
                id=br_id, tenant_id=tenant_id, baseline_id=baseline_id, rsrc_id=r.rsrc_id,
                name=r.name, short_name=r.short_name, rsrc_type=r.rsrc_type, unit_id=r.unit_id,
            )
        )

    assignments = (
        db.query(ResourceAssignment).filter(ResourceAssignment.project_id == project_id).all()
    )
    for a in assignments:
        baseline_rsrc_id = rsrc_row_id_to_baseline_rsrc_id.get(a.resource_id)
        if baseline_rsrc_id is None:
            continue
        db.add(
            BaselineResourceAssignment(
                id=uuid.uuid4(), tenant_id=tenant_id, baseline_id=baseline_id, activity_id=a.activity_id,
                baseline_resource_id=baseline_rsrc_id, target_qty=a.target_qty, target_cost=a.target_cost,
                unit_id=a.unit_id,
            )
        )


def lock_baseline_for_project(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    schedule_import_id: uuid.UUID,
    locked_by_user_id: uuid.UUID,
    version_label: str = "Target-1",
    notes: str | None = None,
) -> Baseline:
    activities = db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all()
    eligible, bac, target_start_date, target_end_date = _compute_baseline_scope(activities)

    existing_active = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == tenant_id, Baseline.project_id == project_id, Baseline.status == BaselineStatus.active)
        .first()
    )
    if existing_active:
        raise BaselineConflictError(
            f"Active baseline '{existing_active.version_label}' already exists. Supersede it first."
        )
    dup = db.query(Baseline).filter(Baseline.project_id == project_id, Baseline.version_label == version_label).first()
    if dup:
        raise BaselineConflictError(f"Version label '{version_label}' already used.")

    baseline_id = _insert_baseline_row(
        db, tenant_id, project_id, schedule_import_id, locked_by_user_id, version_label, notes,
        eligible, bac, target_start_date, target_end_date,
    )
    _populate_baseline_children(db, tenant_id, baseline_id, eligible, bac)
    _snapshot_baseline_resources(db, tenant_id, baseline_id, project_id)

    db.flush()
    return db.get(Baseline, baseline_id)


def _insert_baseline_row(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    schedule_import_id: uuid.UUID,
    locked_by_user_id: uuid.UUID,
    version_label: str,
    notes: str | None,
    eligible: list,
    bac: float,
    target_start_date: date,
    target_end_date: date,
) -> uuid.UUID:
    baseline_id = uuid.uuid4()
    db.add(
        Baseline(
            id=baseline_id, tenant_id=tenant_id, project_id=project_id, schedule_import_id=schedule_import_id,
            version_label=version_label, locked_at=datetime.utcnow(), locked_by_user_id=locked_by_user_id,
            total_budget_manhours=bac, target_start_date=target_start_date, target_end_date=target_end_date,
            distribution_method="linear", status=BaselineStatus.active, activity_count=len(eligible), notes=notes,
        )
    )
    db.flush()
    return baseline_id


def _iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def lock_baseline_from_snapshot(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    schedule_import: ScheduleImport,
    locked_by_user_id: uuid.UUID,
    version_label: str,
) -> Baseline:
    """Lock an EARLIER import (not the live schedule) as the baseline, using the
    per-activity dates/durations frozen on its `activities_snapshot`. Each entry is
    matched to the live activity row by external_id (BaselineActivity points at live
    rows), so activities that no longer exist are skipped. The snapshot doesn't carry
    P6 resource assignments, so a baseline built this way has no frozen resources
    (Baselines -> "Resources in this baseline" reads empty); baselines made from the
    current import via lock_baseline_for_project keep them."""
    snapshot = schedule_import.activities_snapshot or []
    if not snapshot:
        raise BaselineValidationError("This import has no saved activity snapshot to build a baseline from.")

    live = {
        a.external_id: a
        for a in db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
    }
    items = []
    for entry in snapshot:
        row = live.get(entry.get("external_id"))
        if row is None:
            continue
        items.append(
            SimpleNamespace(
                id=row.id,
                target_duration_hours=entry.get("target_duration_hours"),
                planned_start=_iso_date(entry.get("planned_start")),
                early_start=_iso_date(entry.get("early_start")),
                planned_finish=_iso_date(entry.get("planned_finish")),
                early_finish=_iso_date(entry.get("early_finish")),
                wbs_path=entry.get("wbs_path"),
            )
        )
    eligible, bac, target_start_date, target_end_date = _compute_baseline_scope(items)

    baseline_id = _insert_baseline_row(
        db, tenant_id, project_id, schedule_import.id, locked_by_user_id, version_label, None,
        eligible, bac, target_start_date, target_end_date,
    )
    _populate_baseline_children(db, tenant_id, baseline_id, eligible, bac)
    db.flush()
    return db.get(Baseline, baseline_id)


def overwrite_active_baseline(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    schedule_import_id: uuid.UUID,
    locked_by_user_id: uuid.UUID,
) -> Baseline:
    """Replace the current active baseline's frozen data in place — same
    `baselines` row (id, version_label, status), recomputed activities / PV
    curve / resources from the schedule that was just re-imported. Stale
    EvmSnapshot rows for this baseline are dropped; the caller re-derives them
    from surviving progress_entries. The owner chose this over locking a new
    baseline version on every re-upload."""
    baseline = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == tenant_id, Baseline.project_id == project_id, Baseline.status == BaselineStatus.active)
        .first()
    )
    if baseline is None:
        raise BaselineConflictError("No active baseline to overwrite.")

    activities = db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all()
    eligible, bac, target_start_date, target_end_date = _compute_baseline_scope(activities)

    db.query(BaselineResourceAssignment).filter(BaselineResourceAssignment.baseline_id == baseline.id).delete()
    db.query(BaselineResource).filter(BaselineResource.baseline_id == baseline.id).delete()
    db.query(BaselinePvCurve).filter(BaselinePvCurve.baseline_id == baseline.id).delete()
    db.query(BaselineActivity).filter(BaselineActivity.baseline_id == baseline.id).delete()
    db.query(EvmSnapshot).filter(EvmSnapshot.baseline_id == baseline.id).delete()

    baseline.schedule_import_id = schedule_import_id
    baseline.locked_at = datetime.utcnow()
    baseline.locked_by_user_id = locked_by_user_id
    baseline.total_budget_manhours = bac
    baseline.target_start_date = target_start_date
    baseline.target_end_date = target_end_date
    baseline.activity_count = len(eligible)
    db.flush()

    _populate_baseline_children(db, tenant_id, baseline.id, eligible, bac)
    _snapshot_baseline_resources(db, tenant_id, baseline.id, project_id)

    db.flush()
    return baseline
