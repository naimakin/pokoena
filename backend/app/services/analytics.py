"""Dashboard analytics: labor hours and cost, budget vs planned vs actual.

What the Dashboard's charts (KPI strip, gauges, monthly bars, hours by WBS /
activity code, behind-plan table) and the Portfolio's per-project totals read.

Sources, all P6's own numbers from the .xer:
  - budget  — the locked baseline's TASKRSRC lines (BaselineResourceAssignment:
    `target_qty` for RT_Labor hours, `target_cost` over every resource type);
  - current — the current programme's TASKRSRC lines (ResourceAssignment:
    `target_qty` / `act_reg_qty` / `remain_qty`, `*_cost` alike);
  - planned to date — each baseline line spread evenly over its activity's
    baseline start..finish (calendar days, inclusive — the same spread as the
    PV curve, `planned_fraction`) and summed up to the data date;
  - actual by month — each activity's actual units / cost spread evenly over
    actual start..actual finish (or the data date while it is still running).
    P6 keeps no dated actuals in the .xer, so that is the honest split.

Hours are RT_Labor only (nonlabor and material units are in their own unit of
measure); cost is every resource type, since all of it is money. A baseline
locked before resource lines were frozen has none — then the current budget
stands in for it, spread over the same baseline dates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.evm.progress_engine import counts_toward_progress, planned_fraction, wbs_levels
from app.models.activity import Activity, ActivityStatus
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.baseline import Baseline, BaselineActivity, BaselineResource, BaselineResourceAssignment
from app.models.resource import LABOR, Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.wbs_node import WbsNode
from app.services.progress_summary import compute_progress_summary, current_programme, data_date_of
from app.services.schedule_current import get_current_import

# One currency for every money figure POKO shows until projects carry their
# own (P6's CURRTYPE isn't imported yet).
CURRENCY = "EUR"

# Behind plan: how far under the baseline's planned % an unfinished activity
# must be to count, and how many the table lists.
BEHIND_THRESHOLD = 5.0
BEHIND_LIMIT = 10
# Groups shown per grouping before the rest fold into "Other".
GROUP_LIMIT = 20


# --- pure helpers -------------------------------------------------------------


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def spread_by_month(amount: float, start: Optional[date], finish: Optional[date]) -> dict[str, float]:
    """`amount` split evenly over the calendar days start..finish (inclusive),
    summed per month. A missing end collapses onto the other one."""
    if not amount:
        return {}
    start, finish = start or finish, finish or start
    if start is None or finish is None:
        return {}
    if finish < start:
        start, finish = finish, start
    total_days = (finish - start).days + 1
    out: dict[str, float] = {}
    cursor = start
    while cursor <= finish:
        next_month = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        chunk_end = min(finish, next_month - timedelta(days=1))
        days = (chunk_end - cursor).days + 1
        out[month_key(cursor)] = out.get(month_key(cursor), 0.0) + amount * days / total_days
        cursor = next_month
    return out


def _months_between(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# --- per-activity facts -------------------------------------------------------


@dataclass
class ActivityFigures:
    """One activity's hours and cost — budget from the baseline, the rest from
    the current programme."""

    activity: Activity
    baseline_start: Optional[date] = None
    baseline_finish: Optional[date] = None
    in_baseline: bool = False
    budget_hours: float = 0.0  # baseline
    budget_cost: float = 0.0
    current_hours: float = 0.0  # current target_qty
    current_cost: float = 0.0
    actual_hours: float = 0.0
    actual_cost: float = 0.0
    remaining_hours: float = 0.0
    remaining_cost: float = 0.0
    planned_hours: float = 0.0  # baseline, to the data date
    planned_cost: float = 0.0


@dataclass
class Measure:
    budget: float = 0.0
    current_budget: float = 0.0
    planned: float = 0.0
    actual: float = 0.0
    remaining: float = 0.0

    def add(self, budget: float, current: float, planned: float, actual: float, remaining: float) -> None:
        self.budget += budget
        self.current_budget += current
        self.planned += planned
        self.actual += actual
        self.remaining += remaining


def _hours(f: ActivityFigures) -> tuple[float, float, float, float, float]:
    return f.budget_hours, f.current_hours, f.planned_hours, f.actual_hours, f.remaining_hours


def _cost(f: ActivityFigures) -> tuple[float, float, float, float, float]:
    return f.budget_cost, f.current_cost, f.planned_cost, f.actual_cost, f.remaining_cost


def load_figures(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, baseline: Optional[Baseline]
) -> tuple[date, list[ActivityFigures]]:
    current = get_current_import(db, tenant_id, project_id)
    as_of = data_date_of(current)
    activities = [
        a
        for a in current_programme(
            db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id).all(),
            current,
        )
        if counts_toward_progress(a.task_type)
    ]
    figures = {a.id: ActivityFigures(activity=a) for a in activities}

    rows = (
        db.query(
            ResourceAssignment.activity_id,
            Resource.rsrc_type,
            func.coalesce(func.sum(ResourceAssignment.target_qty), 0.0),
            func.coalesce(func.sum(ResourceAssignment.act_reg_qty), 0.0),
            func.coalesce(func.sum(ResourceAssignment.remain_qty), 0.0),
            func.coalesce(func.sum(ResourceAssignment.target_cost), 0.0),
            func.coalesce(func.sum(ResourceAssignment.act_reg_cost), 0.0),
            func.coalesce(func.sum(ResourceAssignment.remain_cost), 0.0),
        )
        .join(Resource, Resource.id == ResourceAssignment.resource_id)
        .filter(ResourceAssignment.tenant_id == tenant_id, ResourceAssignment.project_id == project_id)
        .group_by(ResourceAssignment.activity_id, Resource.rsrc_type)
        .all()
    )
    for activity_id, rsrc_type, qty, act_qty, rem_qty, cost, act_cost, rem_cost in rows:
        f = figures.get(activity_id)
        if f is None:
            continue
        if rsrc_type == LABOR:
            f.current_hours += float(qty)
            f.actual_hours += float(act_qty)
            f.remaining_hours += float(rem_qty)
        f.current_cost += float(cost)
        f.actual_cost += float(act_cost)
        f.remaining_cost += float(rem_cost)

    if baseline is not None:
        for ba in db.query(BaselineActivity).filter(BaselineActivity.baseline_id == baseline.id):
            f = figures.get(ba.activity_id)
            if f is not None:
                f.in_baseline = True
                f.baseline_start, f.baseline_finish = ba.baseline_start, ba.baseline_end
        lines = (
            db.query(
                BaselineResourceAssignment.activity_id,
                BaselineResource.rsrc_type,
                func.coalesce(func.sum(BaselineResourceAssignment.target_qty), 0.0),
                func.coalesce(func.sum(BaselineResourceAssignment.target_cost), 0.0),
            )
            .join(BaselineResource, BaselineResource.id == BaselineResourceAssignment.baseline_resource_id)
            .filter(BaselineResourceAssignment.baseline_id == baseline.id)
            .group_by(BaselineResourceAssignment.activity_id, BaselineResource.rsrc_type)
            .all()
        )
        if lines:
            for activity_id, rsrc_type, qty, cost in lines:
                f = figures.get(activity_id)
                if f is None:
                    continue
                if rsrc_type == LABOR:
                    f.budget_hours += float(qty)
                f.budget_cost += float(cost)
        else:
            for f in figures.values():
                if f.in_baseline:
                    f.budget_hours, f.budget_cost = f.current_hours, f.current_cost
        for f in figures.values():
            share = planned_fraction(f.baseline_start, f.baseline_finish, as_of) if f.in_baseline else 0.0
            f.planned_hours = f.budget_hours * share
            f.planned_cost = f.budget_cost * share
    return as_of, list(figures.values())


def totals(figures: Iterable[ActivityFigures]) -> tuple[Measure, Measure]:
    hours, cost = Measure(), Measure()
    for f in figures:
        hours.add(*_hours(f))
        cost.add(*_cost(f))
    return hours, cost


def has_cost(cost: Measure) -> bool:
    return any(abs(v) > 0.005 for v in (cost.budget, cost.current_budget, cost.actual, cost.remaining))


# --- monthly series -----------------------------------------------------------


@dataclass
class MonthFigures:
    month: str
    planned_hours: float = 0.0
    actual_hours: float = 0.0
    planned_cost: float = 0.0
    actual_cost: float = 0.0


def monthly(figures: list[ActivityFigures], as_of: date) -> list[MonthFigures]:
    """Baseline budget spread over baseline dates, actuals over actual dates
    (an activity with actuals but no actual start books them in the data
    date's month)."""
    cells: dict[str, MonthFigures] = {}

    def cell(key: str) -> MonthFigures:
        if key not in cells:
            cells[key] = MonthFigures(month=key)
        return cells[key]

    for f in figures:
        if f.in_baseline:
            for k, v in spread_by_month(f.budget_hours, f.baseline_start, f.baseline_finish).items():
                cell(k).planned_hours += v
            for k, v in spread_by_month(f.budget_cost, f.baseline_start, f.baseline_finish).items():
                cell(k).planned_cost += v
        if f.actual_hours or f.actual_cost:
            a = f.activity
            start = a.actual_start or as_of
            finish = a.actual_finish or max(as_of, start)
            for k, v in spread_by_month(f.actual_hours, start, finish).items():
                cell(k).actual_hours += v
            for k, v in spread_by_month(f.actual_cost, start, finish).items():
                cell(k).actual_cost += v
    if not cells:
        return []
    keys = sorted(cells)
    return [cells.get(k) or MonthFigures(month=k) for k in _months_between(keys[0], keys[-1])]


# --- groupings ----------------------------------------------------------------


@dataclass
class Group:
    label: str
    hours: Measure = field(default_factory=Measure)
    cost: Measure = field(default_factory=Measure)


@dataclass
class Grouping:
    key: str
    label: str
    groups: list[Group]


def _finish_grouping(key: str, label: str, groups: dict[str, Group]) -> Optional[Grouping]:
    ordered = sorted(
        groups.values(), key=lambda g: (-(g.hours.budget or g.hours.current_budget), -g.cost.budget, g.label)
    )
    if len(ordered) > GROUP_LIMIT:
        other = Group(label="Other")
        for g in ordered[GROUP_LIMIT - 1 :]:
            other.hours.add(g.hours.budget, g.hours.current_budget, g.hours.planned, g.hours.actual, g.hours.remaining)
            other.cost.add(g.cost.budget, g.cost.current_budget, g.cost.planned, g.cost.actual, g.cost.remaining)
        ordered = ordered[: GROUP_LIMIT - 1] + [other]
    # A grouping that puts everything in one bucket says nothing.
    if len(ordered) < 2:
        return None
    return Grouping(key=key, label=label, groups=ordered)


def groupings(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, figures: list[ActivityFigures]
) -> list[Grouping]:
    """Hours and cost by WBS (levels 2 and 3 — level 1 is the project node)
    and by every activity code type in use."""
    nodes = db.query(WbsNode).filter(WbsNode.tenant_id == tenant_id, WbsNode.project_id == project_id).all()
    parent = {n.wbs_id: n.parent_wbs_id for n in nodes}
    name = {n.wbs_id: n.wbs_name for n in nodes}
    level = wbs_levels(parent)

    def ancestor_at(wbs_id: Optional[str], depth: int) -> Optional[str]:
        node = wbs_id
        seen: set[str] = set()
        while node is not None and node not in seen and level.get(node, 0) > depth:
            seen.add(node)
            node = parent.get(node)
        return node if node is not None and level.get(node) == depth else None

    out: list[Grouping] = []
    for depth in (2, 3):
        groups: dict[str, Group] = {}
        for f in figures:
            anc = ancestor_at(f.activity.wbs_path, depth)
            label = name.get(anc, "Unassigned") if anc else "Unassigned"
            g = groups.setdefault(anc or "", Group(label=label))
            g.hours.add(*_hours(f))
            g.cost.add(*_cost(f))
        grouping = _finish_grouping(f"wbs:{depth}", f"WBS level {depth}", groups)
        if grouping:
            out.append(grouping)

    types = (
        db.query(ActivityCodeType)
        .filter(ActivityCodeType.tenant_id == tenant_id, ActivityCodeType.project_id == project_id)
        .order_by(ActivityCodeType.name)
        .all()
    )
    if types:
        values = {
            v.id: v
            for v in db.query(ActivityCodeValue).filter(
                ActivityCodeValue.tenant_id == tenant_id, ActivityCodeValue.project_id == project_id
            )
        }
        by_activity: dict[uuid.UUID, dict[uuid.UUID, uuid.UUID]] = {}
        for activity_id, value_id in db.query(TaskActivityCode.activity_id, TaskActivityCode.code_value_id).filter(
            TaskActivityCode.tenant_id == tenant_id, TaskActivityCode.project_id == project_id
        ):
            v = values.get(value_id)
            if v is not None:
                by_activity.setdefault(activity_id, {})[v.code_type_id] = v.id
        for t in types:
            groups = {}
            for f in figures:
                vid = by_activity.get(f.activity.id, {}).get(t.id)
                v = values.get(vid) if vid else None
                label = (v.name or v.actv_code_id) if v else "Unassigned"
                g = groups.setdefault(str(vid or ""), Group(label=label))
                g.hours.add(*_hours(f))
                g.cost.add(*_cost(f))
            grouping = _finish_grouping(f"code:{t.id}", t.name, groups)
            if grouping:
                out.append(grouping)
    return out


# --- behind plan --------------------------------------------------------------


@dataclass
class BehindRow:
    activity: Activity
    wbs_name: Optional[str]
    planned_pct: float
    actual_pct: float
    baseline_finish: Optional[date]

    @property
    def variance(self) -> float:
        return self.actual_pct - self.planned_pct


def behind_plan(
    figures: list[ActivityFigures], as_of: date, wbs_names: dict[str, str]
) -> tuple[int, list[BehindRow]]:
    """Unfinished baseline activities whose % complete trails the baseline's
    planned % at the data date by more than BEHIND_THRESHOLD points — worst
    first. Returns (how many in all, the top BEHIND_LIMIT)."""
    rows = []
    for f in figures:
        a = f.activity
        if not f.in_baseline or a.status == ActivityStatus.complete:
            continue
        planned = planned_fraction(f.baseline_start, f.baseline_finish, as_of) * 100
        actual = float(a.percent_complete or 0)
        if planned - actual > BEHIND_THRESHOLD:
            rows.append(
                BehindRow(
                    activity=a,
                    wbs_name=wbs_names.get(a.wbs_path or ""),
                    planned_pct=round(planned, 1),
                    actual_pct=round(actual, 1),
                    baseline_finish=f.baseline_finish,
                )
            )
    # Ties (many rows sit at -100: due by now, not started) go oldest baseline
    # finish first — the longest overdue.
    rows.sort(key=lambda r: (r.variance, r.baseline_finish or date.max, r.activity.external_id))
    return len(rows), rows[:BEHIND_LIMIT]


# --- everything the Dashboard reads -------------------------------------------


@dataclass
class ProjectAnalytics:
    data_date: date
    baseline: Baseline
    baseline_start: Optional[date]
    baseline_finish: Optional[date]
    forecast_finish: Optional[date]
    finish_variance_days: Optional[int]
    planned_pct: Optional[float]
    actual_pct: Optional[float]
    spi: Optional[float]
    elapsed_pct: Optional[float]
    hours: Measure
    cost: Optional[Measure]
    months: list[MonthFigures]
    groupings: list[Grouping]
    behind_total: int
    behind: list[BehindRow]


def compute_project_analytics(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, baseline: Baseline
) -> ProjectAnalytics:
    summary = compute_progress_summary(db, tenant_id, project_id, baseline)
    as_of, figures = load_figures(db, tenant_id, project_id, baseline)
    hours, cost = totals(figures)
    b_start = summary.baseline_facts.start or baseline.target_start_date
    b_finish = summary.baseline_facts.finish or baseline.target_end_date
    elapsed = planned_fraction(b_start, b_finish, as_of) * 100 if b_start and b_finish else None
    wbs_names = {
        n.wbs_id: n.wbs_name
        for n in db.query(WbsNode).filter(WbsNode.tenant_id == tenant_id, WbsNode.project_id == project_id)
    }
    behind_total, behind = behind_plan(figures, as_of, wbs_names)
    return ProjectAnalytics(
        data_date=as_of,
        baseline=baseline,
        baseline_start=b_start,
        baseline_finish=b_finish,
        forecast_finish=summary.latest_facts.finish,
        finish_variance_days=summary.finish_variance_days,
        planned_pct=summary.planned_pct,
        actual_pct=summary.actual_pct,
        spi=summary.spi,
        elapsed_pct=round(elapsed, 1) if elapsed is not None else None,
        hours=hours,
        cost=cost if has_cost(cost) else None,
        months=monthly(figures, as_of),
        groupings=groupings(db, tenant_id, project_id, figures),
        behind_total=behind_total,
        behind=behind,
    )
