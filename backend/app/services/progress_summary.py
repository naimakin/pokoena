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
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.evm.progress_engine import (
    VersionFacts,
    VersionRow,
    actual_percent,
    counts_toward_progress,
    planned_percent,
    schedule_performance,
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


def baseline_planned_percent(
    baseline_activities: list[BaselineActivity], activities_by_id: dict[uuid.UUID, Activity], as_of: date
) -> Optional[float]:
    """Planned % from the frozen baseline rows. Task type comes from the live
    activity (BaselineActivity doesn't store it); a row whose activity is gone
    counts as ordinary work."""
    rows = []
    for ba in baseline_activities:
        act = activities_by_id.get(ba.activity_id)
        if act is not None and not counts_toward_progress(act.task_type):
            continue
        rows.append((ba.planned_manhours or 0.0, ba.baseline_start, ba.baseline_end))
    return planned_percent(rows, as_of)


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
