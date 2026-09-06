"""Shared project-status rollup + Eisenhower bucketing for the Execution →
Project Status page.

`compute_status_rollup` is the single source of the three headline verdicts
(Progress / Risk / Quality) and their metrics. It's called two ways:
  - synchronously by `api/routes/project_status.py` for the live "current" view;
  - by `services/xer_import.py` at the end of every .xer import, to freeze one
    `ScheduleStatusSnapshot` row so the page can trend status across UPD-n.

All engines it leans on (DCMA, EVM) are pure functions over already-loaded
SQLAlchemy rows — same pattern as `api/routes/dcma.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.engine.quality.dcma import run_dcma
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship
from app.models.baseline import Baseline, BaselineStatus
from app.models.calendar import Calendar
from app.models.evm_snapshot import EvmSnapshot
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_import import ScheduleImport

# An activity is "Important" if it's on/near the critical path.
_IMPORTANT_FLOAT_DAYS = 5
# "Urgent" if not complete and finishing within this many calendar days of the
# data date (~20 working days) — or already in progress / overdue.
_URGENT_WINDOW_DAYS = 28
# WBS-summary / level-of-effort rows never count as real activities here.
_NON_ACTIVITY_TASK_TYPES = {"TT_WBS", "TT_LOE"}

QUADRANTS = [
    ("focus", "Focus On", True, True),
    ("watch", "Watch Out", True, False),
    ("delegate", "Delegate", False, True),
    ("later", "Later", False, False),
]


@dataclass
class StatusRollup:
    data_date: datetime | None
    spi: float | None
    cpi: float | None
    schedule_recovery_index: float | None
    dcma_score: float
    dcma_status: str
    dcma_flagged_external_ids: set[str] = field(default_factory=set)
    activity_count: int = 0
    critical_count: int = 0
    negative_float_count: int = 0
    overdue_count: int = 0
    percent_complete: float = 0.0
    progress_verdict: str = "NO DATA"
    risk_verdict: str = "LOW"
    quality_verdict: str = "LOW"


# --- verdict thresholds ----------------------------------------------------


def progress_verdict(spi: float | None) -> str:
    if spi is None:
        return "NO DATA"
    if spi >= 1.05:
        return "AHEAD"
    if spi >= 0.95:
        return "ON TRACK"
    return "BEHIND SCHEDULE"


def quality_verdict(score: float) -> str:
    if score >= 85:
        return "HIGH"
    if score >= 65:
        return "MEDIUM"
    return "LOW"


def risk_verdict(
    recovery_index: float | None, negative_float_count: int, finish_slip_days: int | None
) -> str:
    if negative_float_count > 0 or (finish_slip_days is not None and finish_slip_days > 10):
        return "HIGH"
    if recovery_index is None:
        return "LOW"
    if recovery_index > 1.5:
        return "HIGH"
    if recovery_index > 1.1:
        return "MEDIUM"
    return "LOW"


# --- metric helpers ------------------------------------------------------------


def real_activities(activities: list[Activity]) -> list[Activity]:
    return [a for a in activities if (a.task_type or "") not in _NON_ACTIVITY_TASK_TYPES]


def _fallback_spi(activities: list[Activity], dd: datetime) -> float | None:
    """EV/PV from activity durations alone (calendar-unaware) — used only when
    no baseline EVM snapshot exists yet."""
    ev = 0.0
    pv = 0.0
    today = dd.date()
    for a in activities:
        hours = a.target_duration_hours or 0.0
        if hours <= 0:
            continue
        ev += hours * (a.percent_complete or 0) / 100.0
        ps, pf = a.planned_start, a.planned_finish
        if ps and pf and pf > ps:
            frac = (today - ps).days / (pf - ps).days
            frac = min(1.0, max(0.0, frac))
        elif pf and today >= pf:
            frac = 1.0
        else:
            frac = 0.0
        pv += hours * frac
    if pv <= 0:
        return None
    return round(ev / pv, 4)


def _percent_complete(activities: list[Activity]) -> float:
    total_hours = sum(a.target_duration_hours or 0.0 for a in activities)
    if total_hours > 0:
        earned = sum((a.target_duration_hours or 0.0) * (a.percent_complete or 0) / 100.0 for a in activities)
        return round(earned / total_hours * 100.0, 1)
    if not activities:
        return 0.0
    return round(sum(a.percent_complete or 0 for a in activities) / len(activities), 1)


def _recovery_index(
    activities: list[Activity], dd: datetime, baseline_end, hours_per_day: float
) -> float | None:
    critical = [
        a
        for a in activities
        if (a.is_critical or a.is_longest_path) and a.status != ActivityStatus.complete
    ]
    remaining_hours = sum(
        a.remaining_duration_hours
        if a.remaining_duration_hours is not None
        else (a.target_duration_hours or 0.0)
        for a in critical
    )
    if remaining_hours <= 0:
        return None
    finish = baseline_end or max(
        (a.planned_finish for a in activities if a.planned_finish), default=None
    )
    if finish is None:
        return None
    calendar_days_left = (finish - dd.date()).days
    working_days_left = max(1.0, calendar_days_left * 5.0 / 7.0)
    working_hours_left = working_days_left * (hours_per_day or 8.0)
    return round(remaining_hours / working_hours_left, 3)


# --- Eisenhower predicates ---------------------------------------------------


def is_important(a: Activity, hours_per_day: float) -> bool:
    if a.is_critical or a.is_longest_path:
        return True
    tf = a.total_float_hours
    return tf is not None and tf <= _IMPORTANT_FLOAT_DAYS * (hours_per_day or 8.0)


def is_urgent(a: Activity, dd: datetime) -> bool:
    if a.status == ActivityStatus.complete:
        return False
    if a.status == ActivityStatus.in_progress:
        return True
    if a.planned_finish is None:
        return False
    return a.planned_finish <= (dd.date() + timedelta(days=_URGENT_WINDOW_DAYS))


def quadrant_key(a: Activity, dd: datetime, hours_per_day: float) -> str:
    imp = is_important(a, hours_per_day)
    urg = is_urgent(a, dd)
    for key, _label, want_imp, want_urg in QUADRANTS:
        if imp == want_imp and urg == want_urg:
            return key
    return "later"


def is_overdue(a: Activity, dd: datetime) -> bool:
    return (
        a.status != ActivityStatus.complete
        and a.planned_finish is not None
        and a.planned_finish < dd.date()
    )


# --- loading + rollup --------------------------------------------------------


def load_status_inputs(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    """Everything the rollup + the route need, loaded once."""
    activities = (
        db.query(Activity)
        .filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
        .all()
    )
    activity_ids = {a.id for a in activities}
    relationships = (
        db.query(ActivityRelationship)
        .filter(
            ActivityRelationship.tenant_id == tenant_id,
            ActivityRelationship.project_id == project_id,
        )
        .all()
        if activity_ids
        else []
    )
    calendar = (
        db.query(Calendar)
        .filter(Calendar.tenant_id == tenant_id, Calendar.project_id == project_id)
        .first()
    )
    hours_per_day = calendar.hours_per_day if calendar and calendar.hours_per_day else 8.0

    last_import = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc())
        .first()
    )
    latest_snapshot = (
        db.query(EvmSnapshot)
        .filter(EvmSnapshot.tenant_id == tenant_id, EvmSnapshot.project_id == project_id)
        .order_by(EvmSnapshot.snapshot_date.desc())
        .first()
    )
    active_baseline = (
        db.query(Baseline)
        .filter(
            Baseline.tenant_id == tenant_id,
            Baseline.project_id == project_id,
            Baseline.status == BaselineStatus.active,
        )
        .first()
    )
    assigned_activity_ids = {
        row.activity_id
        for row in db.query(ResourceAssignment.activity_id).filter(
            ResourceAssignment.tenant_id == tenant_id,
            ResourceAssignment.project_id == project_id,
        )
    }
    return {
        "activities": activities,
        "relationships": relationships,
        "hours_per_day": hours_per_day,
        "last_import": last_import,
        "latest_snapshot": latest_snapshot,
        "active_baseline": active_baseline,
        "assigned_activity_ids": assigned_activity_ids,
    }


def compute_status_rollup(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> StatusRollup:
    return rollup_from_inputs(load_status_inputs(db, tenant_id, project_id))


def rollup_from_inputs(inputs: dict) -> StatusRollup:
    activities: list[Activity] = inputs["activities"]
    real = real_activities(activities)
    hours_per_day: float = inputs["hours_per_day"]
    last_import: ScheduleImport | None = inputs["last_import"]
    latest_snapshot: EvmSnapshot | None = inputs["latest_snapshot"]
    active_baseline: Baseline | None = inputs["active_baseline"]

    data_date = last_import.data_date if last_import else None
    dd = data_date or datetime.utcnow()

    spi = latest_snapshot.spi if latest_snapshot and latest_snapshot.spi is not None else None
    cpi = latest_snapshot.cpi if latest_snapshot and latest_snapshot.cpi is not None else None
    if spi is None:
        spi = _fallback_spi(real, dd)

    baseline_end = active_baseline.target_end_date if active_baseline else None
    recovery_index = _recovery_index(real, dd, baseline_end, hours_per_day)

    forecast_finish = max((a.planned_finish for a in real if a.planned_finish), default=None)
    finish_slip_days = (
        (forecast_finish - baseline_end).days
        if forecast_finish is not None and baseline_end is not None
        else None
    )

    negative_float_count = sum(
        1 for a in real if a.total_float_hours is not None and a.total_float_hours < 0
    )
    critical_count = sum(1 for a in real if a.is_critical)
    overdue_count = sum(1 for a in real if is_overdue(a, dd))

    dcma_score = 0.0
    dcma_status = "warn"
    flagged: set[str] = set()
    try:
        report = run_dcma(
            activities,
            inputs["relationships"],
            hours_per_day,
            data_date,
            inputs["assigned_activity_ids"],
        )
        dcma_score = report.overall_score
        dcma_status = report.overall_status
        for check in report.checks:
            if check.status in ("fail", "warn"):
                flagged.update(check.details)
    except Exception:  # pragma: no cover - defensive; never fail the caller
        pass

    return StatusRollup(
        data_date=data_date,
        spi=spi,
        cpi=cpi,
        schedule_recovery_index=recovery_index,
        dcma_score=dcma_score,
        dcma_status=dcma_status,
        dcma_flagged_external_ids=flagged,
        activity_count=len(real),
        critical_count=critical_count,
        negative_float_count=negative_float_count,
        overdue_count=overdue_count,
        percent_complete=_percent_complete(real),
        progress_verdict=progress_verdict(spi),
        risk_verdict=risk_verdict(recovery_index, negative_float_count, finish_slip_days),
        quality_verdict=quality_verdict(dcma_score),
    )
