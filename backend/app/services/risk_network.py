"""Builds the QSRA engine's network (engine/risk/qsra.py) from the live
schedule tables.

Everything the hot loop needs is converted once, here, into working hours on
ONE calendar — the project calendar, taken as the calendar most remaining
activities run on. An activity on another calendar is rescaled by the ratio of
the two calendars' working weeks: 70 h on a 7-day x 10 h calendar is one
calendar week, which on a 5 x 8 project calendar is 40 h. That keeps an
iteration free of date arithmetic; only the resulting P-dates are turned back
into calendar dates, through the project calendar's CalendarEngine. It is an
approximation on mixed-calendar programmes, which is what the calibration run
(simulated finish with every factor at 1 vs the CPM finish) exists to expose.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.engine.cpm.calendar_engine import CalendarEngine
from app.engine.durations import activity_hours_per_day
from app.engine.evm.evm_engine import build_calendar_engine
from app.engine.risk.qsra import FF, FS, SF, SS, Network, SimActivity, SimLink
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.calendar import Calendar
from app.models.wbs_node import WbsNode
from app.services.schedule_current import get_current_import, to_naive

MILESTONE_TYPES = {"TT_Mile", "TT_FinMile", "TT_StartMile"}
_SUMMARY_TYPES = {"TT_WBS", "TT_LOE"}
# P6 codes — see engine/cpm/scheduler.py for what each suffix means.
_START_FLOORS = {"CS_MSO", "CS_MSOA", "CS_MANDSTART"}
_FINISH_FLOORS = {"CS_MEO", "CS_MEOA", "CS_MANDFIN"}
HARD_CONSTRAINTS = {"CS_MANDSTART", "CS_MANDFIN"}
_LINK = {LinkType.FS: FS, LinkType.SS: SS, LinkType.FF: FF, LinkType.SF: SF}
_DEFAULT_WEEK_HOURS = 40.0


@dataclass
class ScheduleNetwork:
    network: Network
    activities: list[Activity]  # same order as network.activities
    index_by_external_id: dict[str, int]
    data_date: datetime
    calendar: Optional[CalendarEngine]
    hours_per_day: float
    week_hours: float
    group_names: list[str]
    hard_constraint_ids: list[str]
    open_end_ids: list[str]
    summary_count: int
    descendants_by_wbs: dict[str, set[str]]

    def offset_to_date(self, hours: float) -> date:
        """Working-hour offset from the data date -> calendar date."""
        if hours <= 0:
            return self.data_date.date() + timedelta(days=hours / (self.week_hours / 7.0)) if hours < 0 else self.data_date.date()
        if self.calendar is not None:
            try:
                return self.calendar.add_work_hours(self.data_date, hours).date()
            except ValueError:
                pass
        return (self.data_date + timedelta(days=hours / (self.week_hours / 7.0))).date()

    def hours_to_days(self, hours: float) -> float:
        return hours / self.hours_per_day if self.hours_per_day else hours / 8.0

    def date_to_offset(self, d: date) -> float:
        """Calendar date -> working-hour offset from the data date (end of that day)."""
        end = datetime.combine(d, time(23, 59))
        if self.calendar is not None:
            try:
                return self.calendar.work_hours_between(self.data_date, end)
            except ValueError:
                pass
        return (end - self.data_date).days * self.week_hours / 7.0


def _week_hours(cal: Calendar) -> float:
    total = 0.0
    for day in cal.work_week or []:
        for shift in day.get("shifts", []):
            sh, sm = int(shift["start"][:2]), int(shift["start"][3:5])
            eh, em = int(shift["end"][:2]), int(shift["end"][3:5])
            total += max(0.0, (eh * 60 + em - sh * 60 - sm) / 60.0)
    return total or _DEFAULT_WEEK_HOURS


def current_programme_activities(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> list[Activity]:
    """The live programme — same rule as routes/activities.py::list_activities."""
    query = db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
    current = get_current_import(db, tenant_id, project_id)
    if current is not None:
        query = query.filter((Activity.last_import_id.is_(None)) | (Activity.last_import_id == current.id))
    return query.order_by(Activity.external_id).all()


def _wbs_groups(nodes: list[WbsNode]) -> tuple[dict[str, str], dict[str, str], dict[str, set[str]]]:
    """(wbs_id -> group wbs_id, group wbs_id -> display name, wbs_id -> itself
    and every descendant). The group is the node one level under the root —
    typically an area, building or discipline, which is the level a correlated
    overrun actually shares."""
    parent = {n.wbs_id: n.parent_wbs_id for n in nodes}
    name = {n.wbs_id: (n.wbs_name or n.wbs_short_name or n.wbs_id) for n in nodes}
    group_of: dict[str, str] = {}
    for wid in parent:
        chain = [wid]
        seen = {wid}
        while parent.get(chain[-1]) and parent[chain[-1]] in parent and parent[chain[-1]] not in seen:
            chain.append(parent[chain[-1]])
            seen.add(chain[-1])
        chain.reverse()  # root first
        group_of[wid] = chain[1] if len(chain) > 1 else chain[0]
    children: dict[str, list[str]] = {}
    for wid, p in parent.items():
        if p:
            children.setdefault(p, []).append(wid)
    desc: dict[str, set[str]] = {}

    def collect(w: str) -> set[str]:
        if w in desc:
            return desc[w]
        out = {w}
        stack = list(children.get(w, []))
        while stack:
            c = stack.pop()
            if c in out:
                continue
            out.add(c)
            stack.extend(children.get(c, []))
        desc[w] = out
        return out

    for wid in parent:
        collect(wid)
    return group_of, name, desc


def build_network(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    background_for: Callable[[Activity, float], tuple[float, float, float]],
    *,
    correlate_by_wbs: bool = True,
) -> ScheduleNetwork:
    """`background_for(activity, hours_per_day)` returns its (low, ml, high)
    factors — the caller owns the uncertainty policy."""
    all_acts = current_programme_activities(db, tenant_id, project_id)
    acts = [a for a in all_acts if (a.task_type or "") not in _SUMMARY_TYPES]
    summary_count = len(all_acts) - len(acts)

    current = get_current_import(db, tenant_id, project_id)
    dd = to_naive(current.data_date) if current is not None and current.data_date else None
    if dd is None:
        dd = datetime.combine(date.today(), time(8, 0))

    calendars = {
        c.id: c for c in db.query(Calendar).filter(Calendar.tenant_id == tenant_id, Calendar.project_id == project_id)
    }
    usage = Counter(a.clndr_id for a in acts if a.clndr_id and a.status != ActivityStatus.complete)
    project_cal_row = calendars.get(usage.most_common(1)[0][0]) if usage else next(iter(calendars.values()), None)
    week_hours = _week_hours(project_cal_row) if project_cal_row else _DEFAULT_WEEK_HOURS
    hpd = project_cal_row.hours_per_day if project_cal_row and project_cal_row.hours_per_day else 8.0
    engine: Optional[CalendarEngine] = None
    if project_cal_row is not None:
        try:
            engine = build_calendar_engine(project_cal_row)
        except Exception:  # a malformed stored calendar mustn't sink the analysis
            engine = None

    week_by_cal = {cid: _week_hours(c) for cid, c in calendars.items()}
    hours_per_cal_day = week_hours / 7.0

    def factor(a: Activity) -> float:
        wk = week_by_cal.get(a.clndr_id) if a.clndr_id else None
        return (week_hours / wk) if wk else 1.0

    def approx_offset(d: Optional[date]) -> float:
        # Completed finishes / active starts: precision doesn't move the result.
        return 0.0 if d is None else (d - dd.date()).days * hours_per_cal_day

    def floor_offset(d: date) -> float:
        if engine is not None:
            try:
                return engine.work_hours_between(dd, datetime.combine(d, time(0, 0)))
            except ValueError:
                pass
        return approx_offset(d)

    nodes = db.query(WbsNode).filter(WbsNode.tenant_id == tenant_id, WbsNode.project_id == project_id).all()
    group_of, wbs_name, descendants = _wbs_groups(nodes)
    group_ids: dict[str, int] = {}
    group_names: list[str] = []

    sim: list[SimActivity] = []
    hard: list[str] = []
    for a in acts:
        if a.status == ActivityStatus.complete:
            status = "complete"
        elif a.status == ActivityStatus.in_progress or a.actual_start is not None:
            status = "active"
        else:
            status = "not_started"

        if status == "complete":
            remaining = 0.0
        elif a.remaining_duration_hours is not None:
            remaining = a.remaining_duration_hours
        else:
            remaining = (a.remaining_duration_days or 0) * activity_hours_per_day(a, hpd)
        remaining *= factor(a)

        s_floor = f_floor = None
        if status != "complete":
            for ctype, cdate in ((a.constraint_type, a.constraint_date), (a.constraint_type_2, a.constraint_date_2)):
                if ctype in HARD_CONSTRAINTS:
                    hard.append(a.external_id)
                if cdate is None or cdate <= dd.date():
                    continue
                if ctype in _START_FLOORS and status == "not_started":
                    s_floor = max(s_floor or 0.0, floor_offset(cdate))
                elif ctype in _FINISH_FLOORS:
                    # A finish floor is the END of that working day.
                    f_floor = max(f_floor or 0.0, floor_offset(cdate + timedelta(days=1)))

        group = -1
        if correlate_by_wbs and a.wbs_path and a.wbs_path in group_of:
            gid = group_of[a.wbs_path]
            if gid not in group_ids:
                group_ids[gid] = len(group_ids)
                group_names.append(wbs_name.get(gid, gid))
            group = group_ids[gid]

        sim.append(
            SimActivity(
                key=a.id,
                external_id=a.external_id,
                name=a.name,
                status=status,
                remaining_hours=max(0.0, remaining),
                is_milestone=(a.task_type or "") in MILESTONE_TYPES,
                fixed_finish_offset=min(0.0, approx_offset(a.actual_finish)) if status == "complete" else 0.0,
                fixed_start_offset=min(0.0, approx_offset(a.actual_start)) if status != "not_started" else 0.0,
                start_floor_offset=s_floor,
                finish_floor_offset=f_floor,
                background=(
                    (1.0, 1.0, 1.0) if status == "complete" else background_for(a, activity_hours_per_day(a, hpd))
                ),
                group=group,
            )
        )

    index_by_id = {a.id: i for i, a in enumerate(acts)}
    links: list[SimLink] = []
    has_pred: set[int] = set()
    has_succ: set[int] = set()
    rels = db.query(ActivityRelationship).filter(
        ActivityRelationship.tenant_id == tenant_id, ActivityRelationship.project_id == project_id
    )
    for r in rels:
        p = index_by_id.get(r.predecessor_id)
        s = index_by_id.get(r.successor_id)
        if p is None or s is None:
            continue
        # Lag counts on the predecessor's calendar (P6's default).
        lag = (r.lag_hours or 0.0) * factor(acts[p])
        links.append(SimLink(pred=p, succ=s, kind=_LINK.get(r.link_type, FS), lag_hours=lag))
        has_pred.add(s)
        has_succ.add(p)

    incomplete = [i for i, s in enumerate(sim) if s.status != "complete"]
    open_ends = [
        acts[i].external_id for i in incomplete
        if (i not in has_pred and sim[i].status == "not_started") or i not in has_succ
    ]

    return ScheduleNetwork(
        network=Network(sim, links, n_groups=len(group_ids)),
        activities=acts,
        index_by_external_id={a.external_id: i for i, a in enumerate(acts)},
        data_date=dd,
        calendar=engine,
        hours_per_day=hpd,
        week_hours=week_hours,
        group_names=group_names,
        hard_constraint_ids=sorted(set(hard)),
        open_end_ids=open_ends,
        summary_count=summary_count,
        descendants_by_wbs=descendants,
    )
