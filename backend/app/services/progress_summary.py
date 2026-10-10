"""Planned vs actual progress at the data date, plus the baseline vs latest
version table — what Reporting's "Progress: planned vs actual" block and the
Executive Summary verdict read. The arithmetic lives in
`engine/evm/progress_engine.py`; this module only loads rows.

Also `evm_point_at`, the hours-based EVM point (PV/EV/AC/BAC) AT the data
date. EVM snapshots are only rewritten when progress is submitted, and their
latest row sits at the end of the baseline PV curve (PV = BAC), so reading
"the newest snapshot" reported 100 % planned and a stale EV. Every live
summary reads this instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, undefer

from app.engine.evm.progress_engine import (
    VersionFacts,
    VersionRow,
    actual_percent,
    counts_toward_progress,
    forecast_percent,
    planned_percent,
    schedule_performance,
    update_cadence_days,
    version_facts,
    wbs_levels,
)
from app.engine.evm.scurve_engine import EvmPoint, compute_current_ev
from app.models.activity import Activity, ActivityStatus
from app.models.baseline import Baseline, BaselineActivity, BaselinePvCurve
from app.models.progress_entry import ProgressEntry, ProgressEntryType
from app.models.schedule_import import ScheduleImport
from app.models.wbs_node import WbsNode
from app.services.schedule_current import get_current_import, to_naive

# How Poko arrives at percent complete, stated on every report.
PROGRESS_BASIS = (
    "Duration-weighted: planned from the locked baseline, actual from the current schedule "
    "(Level of Effort and WBS Summary excluded)"
)


def current_programme(activities: list[Activity], current: Optional[ScheduleImport]) -> list[Activity]:
    """Activities dropped from the latest .xer keep their row (and their old
    `last_import_id`) — they are not part of the programme any more."""
    if current is None:
        return activities
    return [a for a in activities if a.last_import_id is None or a.last_import_id == current.id]


def data_date_of(current: Optional[ScheduleImport]) -> date:
    dd = to_naive(current.data_date) if current else None
    return (dd or datetime.utcnow()).date()


def baseline_planned_rows(
    baseline_activities: list[BaselineActivity], activities_by_id: dict[uuid.UUID, Activity]
) -> list[tuple[float, Optional[date], Optional[date]]]:
    """(hours, baseline start, baseline finish) per baseline row that counts
    toward progress — `planned_percent`'s input. Task type comes from the live
    activity (BaselineActivity doesn't store it); a row whose activity is gone
    counts as ordinary work. Build it once when asking for many dates."""
    rows = []
    for ba in baseline_activities:
        act = activities_by_id.get(ba.activity_id)
        if act is not None and not counts_toward_progress(act.task_type):
            continue
        rows.append((ba.planned_manhours or 0.0, ba.baseline_start, ba.baseline_end))
    return rows


def baseline_planned_percent(
    baseline_activities: list[BaselineActivity], activities_by_id: dict[uuid.UUID, Activity], as_of: date
) -> Optional[float]:
    """Planned % from the frozen baseline rows (see baseline_planned_rows)."""
    return planned_percent(baseline_planned_rows(baseline_activities, activities_by_id), as_of)


def programme_actual_percent(activities: list[Activity]) -> Optional[float]:
    return actual_percent(
        (a.target_duration_hours or 0.0, float(a.percent_complete or 0))
        for a in activities
        if counts_toward_progress(a.task_type)
    )


def evm_point_at(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, baseline: Baseline) -> EvmPoint:
    current = get_current_import(db, tenant_id, project_id)
    as_of = data_date_of(current)

    pv_row = (
        db.query(BaselinePvCurve.pv_cumulative)
        .filter(BaselinePvCurve.baseline_id == baseline.id, BaselinePvCurve.curve_date < as_of)
        .order_by(BaselinePvCurve.curve_date.desc())
        .first()
    )
    activities = current_programme(
        db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all(),
        current,
    )
    ac = (
        db.query(func.coalesce(func.sum(ProgressEntry.burned_manhours_daily), 0.0))
        .filter(
            ProgressEntry.project_id == project_id,
            ProgressEntry.entry_type.in_([ProgressEntryType.actual, ProgressEntryType.correction]),
            ProgressEntry.entry_date <= as_of,
        )
        .scalar()
    )
    return EvmPoint.compute(
        as_of,
        float(pv_row[0]) if pv_row else 0.0,
        compute_current_ev(activities),
        float(ac or 0.0),
        baseline.total_budget_manhours,
    )


@dataclass
class ProgressSummary:
    data_date: date
    baseline: Baseline
    baseline_import: Optional[ScheduleImport]
    current_import: Optional[ScheduleImport]
    planned_pct: Optional[float]
    actual_pct: Optional[float]
    spi: Optional[float]
    finish_variance_days: Optional[int]
    baseline_facts: VersionFacts
    latest_facts: VersionFacts


def compute_progress_summary(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, baseline: Baseline
) -> ProgressSummary:
    current = get_current_import(db, tenant_id, project_id)
    as_of = data_date_of(current)

    all_activities = (
        db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all()
    )
    by_id = {a.id: a for a in all_activities}
    programme = current_programme(all_activities, current)
    baseline_rows = db.query(BaselineActivity).filter(BaselineActivity.baseline_id == baseline.id).all()

    # Activity.wbs_path / BaselineActivity.wbs_code hold the P6 wbs_id, not a
    # path — depth comes from the WBS tree.
    level = wbs_levels(
        {
            n.wbs_id: n.parent_wbs_id
            for n in db.query(WbsNode).filter(WbsNode.tenant_id == tenant_id, WbsNode.project_id == project_id)
        }
    )

    planned = baseline_planned_percent(baseline_rows, by_id, as_of)
    actual = programme_actual_percent(programme)

    # Baseline "remaining" is what the baseline still had open at TODAY's data
    # date — so the two rows compare planned-open against actually-open.
    baseline_facts = version_facts(
        VersionRow(
            task_type=by_id[ba.activity_id].task_type if ba.activity_id in by_id else None,
            start=ba.baseline_start,
            finish=ba.baseline_end,
            wbs_level=level.get(ba.wbs_code or "", 0),
            is_remaining=ba.baseline_end is None or ba.baseline_end >= as_of,
        )
        for ba in baseline_rows
    )
    latest_facts = version_facts(
        VersionRow(
            task_type=a.task_type,
            start=a.actual_start or a.early_start or a.planned_start,
            finish=a.actual_finish or a.early_finish or a.planned_finish,
            wbs_level=level.get(a.wbs_path or "", 0),
            is_remaining=a.status != ActivityStatus.complete,
        )
        for a in programme
    )
    variance = (
        (latest_facts.finish - baseline_facts.finish).days
        if latest_facts.finish and baseline_facts.finish
        else None
    )

    return ProgressSummary(
        data_date=as_of,
        baseline=baseline,
        baseline_import=db.get(ScheduleImport, baseline.schedule_import_id),
        current_import=current,
        planned_pct=planned,
        actual_pct=actual,
        spi=schedule_performance(planned, actual),
        finish_variance_days=variance,
        baseline_facts=baseline_facts,
        latest_facts=latest_facts,
    )


# --- progress curve -----------------------------------------------------------


@dataclass
class CurvePoint:
    date: date
    planned: Optional[float] = None
    actual: Optional[float] = None
    forecast: Optional[float] = None


def _month_ends(start: date, end: date) -> list[date]:
    out = []
    y, m = start.year, start.month
    while True:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        last = nxt - timedelta(days=1)
        out.append(last)
        if last >= end:
            return out
        y, m = nxt.year, nxt.month


def numbered_updates(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, *, with_activities: bool = False
) -> list[ScheduleImport]:
    """UPD-1, UPD-2… with a data date, oldest first; one per data date (the
    latest upload wins when an update was re-imported). `with_activities`
    loads every activities_snapshot in the same query (it's deferred)."""
    query = db.query(ScheduleImport)
    if with_activities:
        query = query.options(undefer(ScheduleImport.activities_snapshot))
    rows = (
        query
        .filter(
            ScheduleImport.tenant_id == tenant_id,
            ScheduleImport.project_id == project_id,
            ScheduleImport.revision_no.isnot(None),
            ScheduleImport.data_date.isnot(None),
        )
        .order_by(ScheduleImport.imported_at)
        .all()
    )
    by_date: dict[date, ScheduleImport] = {}
    for r in rows:
        by_date[to_naive(r.data_date).date()] = r
    return [by_date[d] for d in sorted(by_date)]


def compute_progress_curve(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, baseline: Baseline
) -> tuple[date, list[CurvePoint]]:
    """Planned (baseline), actual (one point per schedule update, from each
    import's frozen activity snapshot; the current one from the live rows) and
    forecast (current schedule from the data date on) — all duration-weighted
    percentages on the same basis as `compute_progress_summary`."""
    current = get_current_import(db, tenant_id, project_id)
    as_of = data_date_of(current)

    all_activities = (
        db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all()
    )
    by_id = {a.id: a for a in all_activities}
    programme = [a for a in current_programme(all_activities, current) if counts_toward_progress(a.task_type)]
    baseline_rows = db.query(BaselineActivity).filter(BaselineActivity.baseline_id == baseline.id).all()

    actual_by_date: dict[date, float] = {baseline.target_start_date: 0.0}
    for imp in numbered_updates(db, tenant_id, project_id, with_activities=True):
        dd = to_naive(imp.data_date).date()
        if dd >= as_of or not imp.activities_snapshot:
            continue
        pct = actual_percent(
            (e.get("target_duration_hours") or 0.0, float(e.get("percent_complete") or 0))
            for e in imp.activities_snapshot
            if counts_toward_progress(e.get("task_type"))
        )
        if pct is not None:
            actual_by_date[dd] = pct
    live_actual = programme_actual_percent(programme)
    if live_actual is not None:
        actual_by_date[as_of] = live_actual

    forecast_rows = [
        (
            a.target_duration_hours or 0.0,
            float(a.percent_complete or 0),
            a.actual_start or a.early_start or a.planned_start,
            a.early_finish or a.planned_finish or a.actual_finish,
        )
        for a in programme
    ]
    finishes = [f for *_, f in forecast_rows if f] + [baseline.target_end_date]
    end = max(finishes)

    dates = set(_month_ends(baseline.target_start_date, end)) | set(actual_by_date) | {as_of}
    planned_rows = baseline_planned_rows(baseline_rows, by_id)
    points = []
    for d in sorted(dates):
        points.append(
            CurvePoint(
                date=d,
                planned=planned_percent(planned_rows, d),
                actual=actual_by_date.get(d),
                forecast=forecast_percent(forecast_rows, as_of, d) if d >= as_of else None,
            )
        )
    return as_of, points


# --- current update (Dashboard) -----------------------------------------------


@dataclass
class CurrentUpdate:
    revision_label: Optional[str]
    filename: str
    data_date: date
    imported_at: datetime
    previous_label: Optional[str]
    previous_data_date: Optional[date]
    cadence_days: Optional[int]
    next_data_date: Optional[date]
    activities_total: int
    activities_complete: int
    activities_in_progress: int
    started_this_update: Optional[int]
    finished_this_update: Optional[int]


def compute_current_update(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Optional[CurrentUpdate]:
    """What the latest schedule update says — the Dashboard's fallback when no
    subcontractor update period is running. "This update" is the window
    between the previous update's data date and this one's."""
    current = get_current_import(db, tenant_id, project_id)
    if current is None or current.data_date is None:
        return None
    as_of = to_naive(current.data_date).date()

    updates = numbered_updates(db, tenant_id, project_id)
    earlier = [u for u in updates if to_naive(u.data_date).date() < as_of]
    previous = earlier[-1] if earlier else None
    prev_dd = to_naive(previous.data_date).date() if previous else None
    cadence = update_cadence_days(
        [to_naive(u.data_date).date() for u in updates if to_naive(u.data_date).date() <= as_of]
    )

    programme = [
        a
        for a in current_programme(
            db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all(),
            current,
        )
        if counts_toward_progress(a.task_type)
    ]

    def in_window(d: Optional[date]) -> bool:
        return d is not None and prev_dd is not None and prev_dd <= d < as_of

    return CurrentUpdate(
        revision_label=current.revision_label,
        filename=current.filename,
        data_date=as_of,
        imported_at=current.imported_at,
        previous_label=previous.revision_label if previous else None,
        previous_data_date=prev_dd,
        cadence_days=cadence,
        next_data_date=as_of + timedelta(days=cadence) if cadence else None,
        activities_total=len(programme),
        activities_complete=sum(a.status == ActivityStatus.complete for a in programme),
        activities_in_progress=sum(a.status == ActivityStatus.in_progress for a in programme),
        started_this_update=sum(in_window(a.actual_start) for a in programme) if prev_dd else None,
        finished_this_update=sum(in_window(a.actual_finish) for a in programme) if prev_dd else None,
    )
