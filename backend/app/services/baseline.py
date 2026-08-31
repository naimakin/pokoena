"""Shared "lock the project's current schedule as a baseline" logic.

Used by two callers: the manual `POST /projects/{id}/evm/baseline` action
(app/api/routes/evm.py, company_admin-gated) and the Program Library page's
automatic lock-on-first-import (app/services/xer_import.py, system-triggered,
no role gate — see that module for why the first .xer upload for a project
becomes its baseline automatically). See app/models/baseline.py for the
"Vance Baseline Mandate" (at most one `active` baseline per project).

Does not commit — callers own the transaction boundary (the manual route
commits right after; the import path commits once at the end of import_xer,
alongside the ScheduleImport row itself).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.engine.evm.scurve_engine import generate_pv_curve
from app.models.activity import Activity
from app.models.baseline import Baseline, BaselineActivity, BaselinePvCurve, BaselineStatus


class BaselineLockError(ValueError):
    """Base class for a schedule state that can't be locked as a baseline."""


class BaselineValidationError(BaselineLockError):
    """The schedule itself isn't lockable yet (no BAC, no planned dates)."""


class BaselineConflictError(BaselineLockError):
    """An active baseline or the requested version label already exists."""


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
    target_start_date = min(starts)
    target_end_date = max(ends)

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

    baseline_id = uuid.uuid4()
    db.add(
        Baseline(
            id=baseline_id, tenant_id=tenant_id, project_id=project_id, schedule_import_id=schedule_import_id,
            version_label=version_label, locked_at=datetime.utcnow(), locked_by_user_id=locked_by_user_id,
            total_budget_manhours=round(bac, 4), target_start_date=target_start_date, target_end_date=target_end_date,
            distribution_method="linear", status=BaselineStatus.active, activity_count=len(eligible), notes=notes,
        )
    )

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
        curve_input.append({"planned_manhours": a.target_duration_hours or 0.0, "baseline_start": a_start, "baseline_end": a_end})

    for curve_date, pv_daily, pv_cumulative in generate_pv_curve(curve_input, bac):
        db.add(
            BaselinePvCurve(
                id=uuid.uuid4(), tenant_id=tenant_id, baseline_id=baseline_id,
                curve_date=curve_date, pv_daily=pv_daily, pv_cumulative=pv_cumulative,
            )
        )

    db.flush()
    return db.get(Baseline, baseline_id)
