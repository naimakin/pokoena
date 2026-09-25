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
from app.parser.xer_models import ParsedSchedule


class BaselineLockError(ValueError):
    """Base class for a schedule state that can't be locked as a baseline."""


class BaselineValidationError(BaselineLockError):
    """The schedule itself isn't lockable yet (no BAC, no planned dates)."""


class BaselineConflictError(BaselineLockError):
    """An active baseline or the requested version label already exists."""


def _compute_baseline_scope(
    activities: list[Activity],
) -> tuple[list[Activity], float, date, date]:
    """Baseline scope + BAC + target start/end. Raises BaselineValidationError
    if the schedule isn't lockable yet.

    Scope excludes only WBS Summary rows (TT_WBS) — P6 auto-generates one per
    WBS node purely for legacy rollup-bar compatibility; it isn't a real,
    independently trackable activity and P6's own Activities view never lists
    it as one. Everything else — including 0-duration Start/Finish Milestones,
    Level of Effort and Resource Dependent activities — stays in scope so it
    gets a BaselineActivity row and shows up in date-variance tracking
    (previously only duration-loaded activities did, which silently dropped
    every milestone from "Activities behind" / worst-slip / the variance
    table on Planning > Baselines). Only duration-loaded activities count
    toward BAC: a 0-duration milestone has no manhours to budget under this
    linear-distribution PV curve.
    """
    scope = [a for a in activities if (a.task_type or "") != "TT_WBS"]
    if not scope:
        raise BaselineValidationError("Snapshot has no activities to baseline.")

    duration_loaded = [a for a in scope if (a.target_duration_hours or 0) > 0]
    bac = sum(a.target_duration_hours or 0.0 for a in duration_loaded)
    if bac <= 0:
        raise BaselineValidationError(
            "Snapshot has no duration-loaded activities (BAC = 0). Ensure activities have a target duration."
        )

    starts = [s for s in (a.planned_start or a.early_start for a in scope) if s]
    ends = [e for e in (a.planned_finish or a.early_finish for a in scope) if e]
    if not starts or not ends:
        raise BaselineValidationError("Activities have no planned dates. Run CPM (import a scheduled .xer) first.")
    return scope, round(bac, 4), min(starts), max(ends)


def _populate_baseline_children(
    db: Session, tenant_id: uuid.UUID, baseline_id: uuid.UUID, scope: list[Activity], bac: float
) -> None:
    """Write the BaselineActivity rows (full scope — see _compute_baseline_scope)
    + the linear PV curve for a baseline (duration-loaded activities only; a
    0-duration milestone contributes nothing to a linear budget distribution)."""
    curve_input = []
    for a in scope:
        a_start = a.planned_start or a.early_start
        a_end = a.planned_finish or a.early_finish
        db.add(
            BaselineActivity(
                id=uuid.uuid4(), tenant_id=tenant_id, baseline_id=baseline_id, activity_id=a.id,
                planned_manhours=a.target_duration_hours or 0.0, baseline_start=a_start, baseline_end=a_end,
                wbs_code=a.wbs_path,
            )
        )
        if (a.target_duration_hours or 0) > 0:
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


def unique_baseline_label(db: Session, project_id: uuid.UUID) -> str:
    """"Baseline" for a project's first lock, "Baseline r2"/"r3"/... after
    that — used whenever a new baseline is locked without the caller
    supplying its own label (Planning -> Baselines upload)."""
    existing = {
        b.version_label
        for b in db.query(Baseline.version_label).filter(Baseline.project_id == project_id).all()
    }
    if "Baseline" not in existing:
        return "Baseline"
    n = 2
    while f"Baseline r{n}" in existing:
        n += 1
    return f"Baseline r{n}"


def _scope_from_parsed(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, parsed_activities: list
) -> list:
    """Match a freshly-uploaded baseline .xer's own activities to the
    project's LIVE Activity rows by task_code (== external_id), so
    BaselineActivity can point at a real row's id without ever writing the
    baseline file's dates/durations into that live row. An activity in the
    baseline file that doesn't exist live (scope differs from the current
    update) is skipped, same policy as lock_baseline_from_snapshot below."""
    live = {
        a.external_id: a
        for a in db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
    }
    items = []
    for act in parsed_activities:
        row = live.get(act.task_code)
        if row is None:
            continue
        items.append(
            SimpleNamespace(
                id=row.id,
                task_type=act.task_type,
                target_duration_hours=act.target_drtn_hr_cnt,
                planned_start=act.target_start_date.date() if act.target_start_date else None,
                early_start=act.early_start_date.date() if act.early_start_date else None,
                planned_finish=act.target_end_date.date() if act.target_end_date else None,
                early_finish=act.early_end_date.date() if act.early_end_date else None,
                wbs_path=act.wbs_id,
            )
        )
    return items


def _snapshot_baseline_resources_from_parsed(
    db: Session, tenant_id: uuid.UUID, baseline_id: uuid.UUID, project_id: uuid.UUID, parsed: ParsedSchedule
) -> None:
    """Same as _snapshot_baseline_resources but sourced from the baseline
    .xer's OWN parsed resources/assignments instead of the live tables — used
    when a baseline is (re-)locked without overwriting the project's live
    schedule (see lock_baseline_from_parsed/overwrite_active_baseline_from_parsed)."""
    live_by_task_code = {
        a.external_id: a
        for a in db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
    }
    rsrc_id_to_baseline_rsrc_id: dict[str, uuid.UUID] = {}
    for res in parsed.resources:
        br_id = uuid.uuid4()
        rsrc_id_to_baseline_rsrc_id[res.rsrc_id] = br_id
        db.add(
            BaselineResource(
                id=br_id, tenant_id=tenant_id, baseline_id=baseline_id, rsrc_id=res.rsrc_id,
                name=res.rsrc_name, short_name=res.rsrc_short_name, rsrc_type=res.rsrc_type, unit_id=res.unit_id,
            )
        )

    acts_by_task_id = {a.task_id: a for a in parsed.activities}
    for assign in parsed.assignments:
        baseline_rsrc_id = rsrc_id_to_baseline_rsrc_id.get(assign.rsrc_id)
        act = acts_by_task_id.get(assign.task_id)
        live_row = live_by_task_code.get(act.task_code) if act else None
        if baseline_rsrc_id is None or live_row is None:
            continue
        db.add(
            BaselineResourceAssignment(
                id=uuid.uuid4(), tenant_id=tenant_id, baseline_id=baseline_id, activity_id=live_row.id,
                baseline_resource_id=baseline_rsrc_id, target_qty=assign.target_qty, target_cost=assign.target_cost,
                unit_id=assign.unit_id,
            )
        )


def lock_baseline_from_parsed(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    parsed: ParsedSchedule,
    schedule_import_id: uuid.UUID,
    locked_by_user_id: uuid.UUID,
    version_label: str,
) -> Baseline:
    """Lock a freshly-uploaded baseline .xer as the project's Performance
    Measurement Baseline WITHOUT touching the live schedule tables — used for
    every Planning -> Baselines upload except a project's very first import
    (which has no separate "current" yet, so it locks from the live tables
    via lock_baseline_for_project instead; see services/xer_import.py). The
    frozen dates/durations/BAC come from THIS file, never from whatever the
    live schedule currently says, so re-uploading/replacing the baseline can
    no longer clobber "Current update"."""
    scope = _scope_from_parsed(db, tenant_id, project_id, parsed.activities)
    scope, bac, target_start_date, target_end_date = _compute_baseline_scope(scope)

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
        db, tenant_id, project_id, schedule_import_id, locked_by_user_id, version_label, None,
        scope, bac, target_start_date, target_end_date,
    )
    _populate_baseline_children(db, tenant_id, baseline_id, scope, bac)
    _snapshot_baseline_resources_from_parsed(db, tenant_id, baseline_id, project_id, parsed)

    db.flush()
    return db.get(Baseline, baseline_id)


def overwrite_active_baseline_from_parsed(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    parsed: ParsedSchedule,
    schedule_import_id: uuid.UUID,
    locked_by_user_id: uuid.UUID,
) -> Baseline:
    """Same as overwrite_active_baseline but sourced from a freshly-uploaded
    baseline .xer's own parsed data instead of the live schedule tables — see
    lock_baseline_from_parsed."""
    baseline = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == tenant_id, Baseline.project_id == project_id, Baseline.status == BaselineStatus.active)
        .first()
    )
    if baseline is None:
        raise BaselineConflictError("No active baseline to overwrite.")

    scope = _scope_from_parsed(db, tenant_id, project_id, parsed.activities)
    scope, bac, target_start_date, target_end_date = _compute_baseline_scope(scope)

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
    baseline.activity_count = len(scope)
    db.flush()

    _populate_baseline_children(db, tenant_id, baseline.id, scope, bac)
    _snapshot_baseline_resources_from_parsed(db, tenant_id, baseline.id, project_id, parsed)

    db.flush()
    return baseline


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
    scope, bac, target_start_date, target_end_date = _compute_baseline_scope(activities)

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
        scope, bac, target_start_date, target_end_date,
    )
    _populate_baseline_children(db, tenant_id, baseline_id, scope, bac)
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
    scope: list,
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
            distribution_method="linear", status=BaselineStatus.active, activity_count=len(scope), notes=notes,
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
                task_type=entry.get("task_type"),
                target_duration_hours=entry.get("target_duration_hours"),
                planned_start=_iso_date(entry.get("planned_start")),
                early_start=_iso_date(entry.get("early_start")),
                planned_finish=_iso_date(entry.get("planned_finish")),
                early_finish=_iso_date(entry.get("early_finish")),
                wbs_path=entry.get("wbs_path"),
            )
        )
    scope, bac, target_start_date, target_end_date = _compute_baseline_scope(items)

    baseline_id = _insert_baseline_row(
        db, tenant_id, project_id, schedule_import.id, locked_by_user_id, version_label, None,
        scope, bac, target_start_date, target_end_date,
    )
    _populate_baseline_children(db, tenant_id, baseline_id, scope, bac)
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
    scope, bac, target_start_date, target_end_date = _compute_baseline_scope(activities)

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
    baseline.activity_count = len(scope)
    db.flush()

    _populate_baseline_children(db, tenant_id, baseline.id, scope, bac)
    _snapshot_baseline_resources(db, tenant_id, baseline.id, project_id)

    db.flush()
    return baseline
