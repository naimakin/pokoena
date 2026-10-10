"""Portfolio Dashboard: every project the user can see, side by side.

Per project:
  - the scorecard (SPI, planned vs actual %, start, forecast vs baseline
    finish, DCMA quality score) and the three Progress / Risk / Quality
    verdicts — from the rollup Execution > Project Status uses
    (services/project_status.py), run over the current programme;
  - a month-by-month criticality timeline: for each month, the Criticality
    Scores (services/criticality.py) of the activities active in it, summed,
    plus how many tasks / critical tasks / delay drivers fall in it. A month
    full of high-scoring work is where the programme needs watching.

The portfolio row is the per-month sum across projects. Completed work has no
Criticality Score (it can't slip any more), so finished months read calm by
construction — the timeline shows where the risk still is, not where it was.

Activities are the current programme's only (same rule as GET /activities),
WBS-summary / LOE rows excluded (services/project_status.py::real_activities).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.durations import activity_days
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user_tenant_role import TenantRole
from app.services.analytics import Measure, has_cost, load_figures, totals
from app.services.criticality import criticality, shown_dates
from app.services.project_status import load_status_inputs, real_activities, rollup_from_inputs
from app.services.schedule_current import get_current_import

# Progress buckets on SPI — Project Status's three verdicts split one step finer
# so a portfolio can tell "a little behind" from "behind".
_AHEAD = 1.05
_ON_SCHEDULE = 0.95
_SLIGHTLY_BEHIND = 0.85


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def _month_from_index(i: int) -> str:
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def progress_bucket(spi: Optional[float]) -> str:
    if spi is None:
        return "no_data"
    if spi >= _AHEAD:
        return "ahead"
    if spi >= _ON_SCHEDULE:
        return "on_schedule"
    if spi >= _SLIGHTLY_BEHIND:
        return "slightly_behind"
    return "behind"


@dataclass
class MonthCell:
    month: str
    score: int = 0
    tasks: int = 0
    critical: int = 0  # unfinished, total float <= 0
    delay_drivers: int = 0  # unfinished, negative total float


@dataclass
class ScoredActivity:
    activity: Activity
    score: Optional[int]
    breakdown: Optional[dict]
    start: Optional[date]
    finish: Optional[date]


@dataclass
class ProjectPortfolio:
    project: Project
    has_schedule: bool
    data_date: Optional[datetime] = None
    activity_count: int = 0
    spi: Optional[float] = None
    planned_pct: Optional[float] = None
    actual_pct: Optional[float] = None
    start: Optional[date] = None  # earliest shown Start (actual or early)
    actual_start: Optional[date] = None
    forecast_finish: Optional[date] = None
    baseline_finish: Optional[date] = None
    finish_variance_days: Optional[int] = None
    quality_score: Optional[float] = None
    progress: str = "no_data"
    risk: str = "LOW"
    quality: str = "LOW"
    critical_count: int = 0
    negative_float_count: int = 0
    months: list[MonthCell] = field(default_factory=list)
    scored: list[ScoredActivity] = field(default_factory=list)
    has_baseline: bool = False
    # Labor hours / cost, budget vs planned vs actual (services/analytics.py);
    # cost is None when the programme carries none.
    hours: Optional[Measure] = None
    cost: Optional[Measure] = None


def visible_projects(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, role: TenantRole) -> list[Project]:
    """Same visibility as GET /projects: a company admin sees the tenant, an
    employee the projects they're a member of."""
    query = db.query(Project).filter(Project.tenant_id == tenant_id)
    if role == TenantRole.company_employee:
        query = query.join(ProjectMembership, ProjectMembership.project_id == Project.id).filter(
            ProjectMembership.user_id == user_id
        )
    return query.order_by(Project.name).all()


def _current_programme(activities: list[Activity], current_import_id: Optional[uuid.UUID]) -> list[Activity]:
    if current_import_id is None:
        return activities
    return [a for a in activities if a.last_import_id is None or a.last_import_id == current_import_id]


def _planned_pct(activities: list[Activity], dd: date) -> Optional[float]:
    """Share of the work (duration-weighted) the current schedule's own
    planned dates had done by the data date — only used when no baseline is
    locked (otherwise the rollup's baseline planned % wins)."""
    total = planned = 0.0
    for a in activities:
        hours = a.target_duration_hours or 0.0
        if hours <= 0:
            continue
        total += hours
        ps, pf = a.planned_start, a.planned_finish
        if ps and pf and pf > ps:
            frac = min(1.0, max(0.0, (dd - ps).days / (pf - ps).days))
        elif pf and dd >= pf:
            frac = 1.0
        else:
            frac = 0.0
        planned += hours * frac
    return round(planned / total * 100, 1) if total > 0 else None


def successor_counts(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = (
        db.query(ActivityRelationship.predecessor_id, func.count(ActivityRelationship.id))
        .filter(ActivityRelationship.tenant_id == tenant_id, ActivityRelationship.project_id == project_id)
        .group_by(ActivityRelationship.predecessor_id)
        .all()
    )
    return {pred_id: count for pred_id, count in rows}


def score_activities(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, activities: list[Activity]
) -> list[ScoredActivity]:
    """Each activity's Criticality Score and shown Start/Finish, against the
    programme's own span (services/criticality.py)."""
    spans = [shown_dates(a) for a in activities]
    starts = [s for s, _ in spans if s]
    finishes = [f for _, f in spans if f]
    project_days = (max(finishes) - min(starts)).days + 1 if starts and finishes else None
    successors = successor_counts(db, tenant_id, project_id)
    out = []
    for a, (start, finish) in zip(activities, spans):
        result = criticality(a, project_days, successors.get(a.id, 0))
        out.append(
            ScoredActivity(
                activity=a,
                score=result.score if result else None,
                breakdown=result.breakdown if result else None,
                start=start,
                finish=finish,
            )
        )
    return out


def _months(scored: list[ScoredActivity]) -> list[MonthCell]:
    cells: dict[int, MonthCell] = {}
    for s in scored:
        start, finish = s.start or s.finish, s.finish or s.start
        if start is None or finish is None:
            continue
        if finish < start:
            start, finish = finish, start
        a = s.activity
        unfinished = a.status != ActivityStatus.complete
        tf = a.total_float_hours
        for i in range(_month_index(start), _month_index(finish) + 1):
            cell = cells.get(i)
            if cell is None:
                cell = cells[i] = MonthCell(month=_month_from_index(i))
            cell.tasks += 1
            cell.score += s.score or 0
            if unfinished and tf is not None and tf <= 0.01:
                cell.critical += 1
            if unfinished and tf is not None and tf < -0.01:
                cell.delay_drivers += 1
    if not cells:
        return []
    lo, hi = min(cells), max(cells)
    return [cells.get(i) or MonthCell(month=_month_from_index(i)) for i in range(lo, hi + 1)]


def project_timeline(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> tuple[list[MonthCell], list[ScoredActivity]]:
    """One project's month-by-month criticality timeline and its scored
    activities — what the portfolio row shows for it, without the Project
    Status rollup (DCMA etc.) the scorecard needs. The Dashboard's Project
    Timeline and the timeline's month drill-down read this."""
    current = get_current_import(db, tenant_id, project_id)
    activities = real_activities(
        _current_programme(
            db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all(),
            current.id if current else None,
        )
    )
    scored = score_activities(db, tenant_id, project_id, activities)
    return _months(scored), scored


def top_critical(scored: list[ScoredActivity], limit: int) -> list[ScoredActivity]:
    """Unfinished activities with a Criticality Score, highest first."""
    ranked = [s for s in scored if s.score is not None]
    ranked.sort(key=lambda s: (-(s.score or 0), s.activity.external_id))
    return ranked[:limit]


def project_portfolio(db: Session, tenant_id: uuid.UUID, project: Project) -> ProjectPortfolio:
    inputs = load_status_inputs(db, tenant_id, project.id)
    current = inputs["last_import"]
    programme = _current_programme(inputs["activities"], current.id if current else None)
    activities = real_activities(programme)
    if not activities:
        return ProjectPortfolio(project=project, has_schedule=False)

    # The rollup (and the DCMA run inside it) over the current programme only
    # — it filters to real activities itself.
    inputs["activities"] = programme
    rollup = rollup_from_inputs(inputs)
    dd = (rollup.data_date or datetime.utcnow()).date()

    scored = score_activities(db, tenant_id, project.id, activities)
    actual_starts = [a.actual_start for a in activities if a.actual_start]
    finishes = [s.finish for s in scored if s.finish]
    starts = [s.start for s in scored if s.start]
    forecast_finish = max(finishes) if finishes else None
    baseline = inputs["active_baseline"]
    baseline_finish = (
        baseline.target_end_date
        if baseline is not None
        else max((a.planned_finish for a in activities if a.planned_finish), default=None)
    )

    _, figures = load_figures(db, tenant_id, project.id, baseline)
    hours, cost = totals(figures)

    return ProjectPortfolio(
        project=project,
        has_schedule=True,
        has_baseline=baseline is not None,
        hours=hours,
        cost=cost if has_cost(cost) else None,
        data_date=rollup.data_date,
        activity_count=rollup.activity_count,
        spi=rollup.spi,
        planned_pct=rollup.planned_percent if rollup.planned_percent is not None else _planned_pct(activities, dd),
        actual_pct=rollup.percent_complete,
        start=min(starts) if starts else None,
        actual_start=min(actual_starts) if actual_starts else None,
        forecast_finish=forecast_finish,
        baseline_finish=baseline_finish,
        finish_variance_days=(
            (forecast_finish - baseline_finish).days if forecast_finish and baseline_finish else None
        ),
        quality_score=rollup.dcma_score,
        progress=progress_bucket(rollup.spi),
        risk=rollup.risk_verdict,
        quality=rollup.quality_verdict,
        critical_count=rollup.critical_count,
        negative_float_count=rollup.negative_float_count,
        months=_months(scored),
        scored=scored,
    )


def portfolio_months(projects: list[ProjectPortfolio]) -> list[MonthCell]:
    """The portfolio row: every project's months, summed."""
    cells: dict[str, MonthCell] = {}
    for p in projects:
        for m in p.months:
            cell = cells.setdefault(m.month, MonthCell(month=m.month))
            cell.score += m.score
            cell.tasks += m.tasks
            cell.critical += m.critical
            cell.delay_drivers += m.delay_drivers
    if not cells:
        return []
    keys = sorted(cells)
    lo = _month_index(date(int(keys[0][:4]), int(keys[0][5:]), 1))
    hi = _month_index(date(int(keys[-1][:4]), int(keys[-1][5:]), 1))
    return [cells.get(_month_from_index(i)) or MonthCell(month=_month_from_index(i)) for i in range(lo, hi + 1)]


def activities_in_month(scored: list[ScoredActivity], month: str) -> list[ScoredActivity]:
    """The activities active in `month` ("YYYY-MM"), most critical first."""
    target = int(month[:4]) * 12 + int(month[5:7]) - 1
    out = []
    for s in scored:
        start, finish = s.start or s.finish, s.finish or s.start
        if start is None or finish is None:
            continue
        lo, hi = sorted((_month_index(start), _month_index(finish)))
        if lo <= target <= hi:
            out.append(s)
    out.sort(key=lambda s: (s.score is None, -(s.score or 0), s.activity.external_id))
    return out


def float_days(a: Activity) -> Optional[float]:
    return activity_days(a, a.total_float_hours)
