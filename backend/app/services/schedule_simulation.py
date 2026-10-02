"""Schedule Simulation: what-if runs on a copy of the live programme.

The user picks a simulation data date and a few hypothetical changes (mark an
activity complete, push its finish out three weeks, change what's left of
it...). Nothing is written: the current programme is read from the database
into the CPM engine's working shape, the changes are applied to that copy, and
the copy is rescheduled with P6's default option, Retained Logic
(engine/cpm/scheduler.py, `retained_logic=True`).

Three runs, all on the same engine:

    current    the programme as it stands, at the current data date
    unchanged  the programme as it stands, at the simulation data date
    simulated  the programme with the changes, at the simulation data date

The headline compares `simulated` with `unchanged`, so what it reports is the
effect of the changes alone. Moving the data date without progress pushes every
piece of unfinished work along with it (P6 does exactly that on F9); that
effect is `unchanged` vs `current`, reported as a count and a finish delta, not
mixed in. P6's own stored dates are never diffed: our CPM doesn't reproduce
P6's figures to the hour on every file, and Poko-entered progress isn't
rescheduled in the live tables, so a diff against them would report movement
before any change was made.

Every moved activity says why it moved: the forward pass records each
activity's binding relationships (`driven_by`, `driving_rels`), and a
breadth-first walk from the changed activities along those links gives every
moved activity its `cause` — the step before it on the shortest driving chain
back to a change. An activity that moved later is traced through the simulated
run's links; one that moved earlier through the unchanged run's (what held it
before the change released it).
"""

from __future__ import annotations

import copy
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.engine.cpm.calendar_engine import CalendarEngine, NoWorkingDayError
from app.engine.cpm.scheduler import CpmCycleError, schedule
from app.engine.durations import valid_hours_per_day
from app.engine.evm.evm_engine import calendar_row_to_parsed
from app.models.activity import (
    FINISH_MILESTONE,
    MILESTONE_TYPES,
    P6_STATUS_CODE,
    START_MILESTONE,
    Activity,
    ActivityStatus,
)
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.schedule_import import ScheduleImport
from app.models.wbs_node import WbsNode
from app.parser.xer_models import Activity as EngineActivity
from app.parser.xer_models import ParsedSchedule, ProjectMeta, Relationship
from app.services.risk_network import current_programme_activities
from app.services.schedule_current import get_current_import, to_naive

EDIT_KINDS = (
    "progress", "complete", "actual_start", "percent_complete", "remaining_duration", "finish_delay", "finish_on",
)
MILESTONE_EDIT_KINDS = ("progress", "complete", "finish_delay", "finish_on")
MAX_EDITS = 200
MAX_ROWS = 2000

_SUMMARY_TYPES = {"TT_WBS", "TT_LOE"}
_FINISH_CONSTRAINTS = {"CS_MEO", "CS_MEOA", "CS_MEOB", "CS_MEON", "CS_MANDFIN"}
_STATUS_OF_CODE = {"TK_NotStart": "not_started", "TK_Active": "in_progress", "TK_Complete": "complete"}
_LINK_OF_TYPE = {"PR_FS": "FS", "PR_SS": "SS", "PR_FF": "FF", "PR_SF": "SF"}
_CONSTRAINT_LABELS = {
    "CS_MSO": "Start on",
    "CS_MSOA": "Start on or after",
    "CS_MSOB": "Start on or before",
    "CS_MEO": "Finish on",
    "CS_MEOA": "Finish on or after",
    "CS_MEOB": "Finish on or before",
    "CS_MANDSTART": "Mandatory start",
    "CS_MANDFIN": "Mandatory finish",
    "CS_ALAP": "As late as possible",
}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_TOL = 0.01  # hours


def p6_date(d: date | datetime | None) -> str:
    """DD-MMM-YYYY, independent of the server's locale."""
    if d is None:
        return "—"
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def _fmt_days(days: float) -> str:
    rounded = round(days, 1)
    return f"{rounded:g}d"


class SimulationError(ValueError):
    """Why a simulation can't run. `code` is what the page keys off:
    no_schedule, no_data_date, data_date_before_current, invalid_edits,
    logic_cycle, calendar."""

    def __init__(self, code: str, message: str, errors: Optional[list[dict]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = errors or []

    def detail(self) -> dict:
        out: dict = {"code": self.code, "message": self.message}
        if self.errors:
            out["errors"] = self.errors
        return out


@dataclass
class SimEdit:
    """One hypothetical change.

    kind="progress" is the activity edited the way Project Activities edits it
    — any of status, actual start / finish, % complete, remaining duration —
    plus P6's Expected Finish or "finishes N working days later". Days are the
    activity's OWN calendar days.

    The single-field kinds (complete, actual_start, percent_complete,
    remaining_duration, finish_delay, finish_on) carry their one input in
    `value`: a date for complete / actual_start / finish_on, a number for the
    rest."""

    external_id: str
    kind: str
    value: float | date | None = None
    actual_start: Optional[date] = None
    status: Optional[str] = None  # not_started / in_progress / complete
    actual_finish: Optional[date] = None
    percent_complete: Optional[float] = None
    remaining_days: Optional[float] = None
    expected_finish: Optional[date] = None
    finish_delay_days: Optional[float] = None


@dataclass
class SimSource:
    """The live programme in the engine's working shape. task_id = str(Activity.id)."""

    parsed: ParsedSchedule
    rows: dict[str, Activity]
    task_id_of: dict[str, str]  # external_id -> task_id
    cals: dict[str, CalendarEngine]
    default_clndr: Optional[str]
    data_date: datetime
    current_import: ScheduleImport
    excluded_summary: int
    wbs_names: dict[str, str] = field(default_factory=dict)  # P6 wbs_id -> its name
    warnings: list[dict] = field(default_factory=list)

    def cal(self, act: EngineActivity) -> CalendarEngine:
        found = self.cals.get(act.clndr_id or "") or self.cals.get(self.default_clndr or "")
        if found is None:
            raise SimulationError("calendar", "The programme has no calendar to schedule it on.")
        return found

    def hpd(self, act: EngineActivity) -> float:
        return valid_hours_per_day(self.cal(act)._cal.hours_per_day)


# --- database -> engine ----------------------------------------------------------


def _work_start(cal: CalendarEngine, d: date) -> datetime:
    midnight = datetime.combine(d, time(0, 0))
    return cal._day_work_start(midnight) or midnight


def _work_end(cal: CalendarEngine, d: date) -> datetime:
    midnight = datetime.combine(d, time(0, 0))
    return cal._day_work_end(midnight) or datetime.combine(d, time(23, 59))


def build_sim_source(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> SimSource:
    current = get_current_import(db, tenant_id, project_id)
    if current is None:
        raise SimulationError("no_schedule", "Import a programme first: simulation runs on the current programme.")
    dd = to_naive(current.data_date)
    if dd is None:
        raise SimulationError(
            "no_data_date",
            "This programme has no data date, so a simulation can't start from it. Re-export it from P6 with one.",
        )

    all_rows = current_programme_activities(db, tenant_id, project_id)
    rows = [a for a in all_rows if (a.task_type or "") not in _SUMMARY_TYPES]

    cal_rows = db.query(Calendar).filter(Calendar.tenant_id == tenant_id, Calendar.project_id == project_id).all()
    parsed_cals = [calendar_row_to_parsed(c, clndr_id=str(c.id)) for c in cal_rows]
    cals = {c.clndr_id: CalendarEngine(c) for c in parsed_cals}
    # The project calendar: the one most unfinished work runs on (as QSRA).
    usage = Counter(str(a.clndr_id) for a in rows if a.clndr_id and a.status != ActivityStatus.complete)
    default_clndr = usage.most_common(1)[0][0] if usage else (parsed_cals[0].clndr_id if parsed_cals else None)
    if default_clndr is None:
        raise SimulationError("calendar", "The programme has no calendar to schedule it on.")

    warnings: list[dict] = []
    late_actuals = 0
    acts: list[EngineActivity] = []
    by_id: dict[str, Activity] = {}
    for row in rows:
        key = str(row.id)
        clndr = str(row.clndr_id) if row.clndr_id and str(row.clndr_id) in cals else default_clndr
        cal = cals[clndr]
        hpd = valid_hours_per_day(cal._cal.hours_per_day)
        status_code = P6_STATUS_CODE.get(row.status, "TK_NotStart")

        act_start = _work_start(cal, row.actual_start) if row.actual_start and status_code != "TK_NotStart" else None
        act_end = _work_end(cal, row.actual_finish) if row.actual_finish and status_code == "TK_Complete" else None
        if status_code == "TK_Complete" and act_end is None:
            act_end = act_start or dd
        # An actual on the data date's own day is fine; one on a later day is
        # recorded progress P6 wouldn't accept — held at the data date, counted.
        if (row.actual_finish and act_end is not None and row.actual_finish > dd.date()) or (
            row.actual_start and act_start is not None and row.actual_start > dd.date()
        ):
            late_actuals += 1
        if act_end is not None and act_end > dd:
            act_end = dd
        if act_start is not None and act_start > dd:
            act_start = min(dd, act_end) if act_end else dd
        if act_start is None and status_code == "TK_Complete":
            act_start = act_end

        if status_code == "TK_Complete":
            remaining = 0.0
        elif row.remaining_duration_hours is not None:
            remaining = float(row.remaining_duration_hours)
        else:
            remaining = float(row.remaining_duration_days or 0) * hpd
        target = row.target_duration_hours if row.target_duration_hours is not None else remaining

        def cstr(ctype: Optional[str], cdate: Optional[date]) -> Optional[datetime]:
            if not ctype or cdate is None:
                return None
            return _work_end(cal, cdate) if ctype in _FINISH_CONSTRAINTS else _work_start(cal, cdate)

        acts.append(
            EngineActivity(
                task_id=key,
                proj_id=str(project_id),
                wbs_id=None,
                clndr_id=clndr,
                task_code=row.external_id,
                task_name=row.name,
                task_type=row.task_type or "TT_Task",
                status_code=status_code,
                phys_complete_pct=float(row.phys_complete_pct or 0),
                target_drtn_hr_cnt=float(target or 0),
                remain_drtn_hr_cnt=max(0.0, remaining),
                act_start_date=act_start,
                act_end_date=act_end,
                cstr_type=row.constraint_type,
                cstr_date=cstr(row.constraint_type, row.constraint_date),
                cstr_type2=row.constraint_type_2,
                cstr_date2=cstr(row.constraint_type_2, row.constraint_date_2),
            )
        )
        by_id[key] = row

    if late_actuals:
        warnings.append(
            {
                "code": "late_actuals",
                "external_id": None,
                "message": f"{late_actuals} activit{'ies have' if late_actuals != 1 else 'y has'} actual dates after "
                "the data date in the live schedule; they're treated as reached at the data date.",
            }
        )

    hpd_of = {a.task_id: valid_hours_per_day(cals[a.clndr_id]._cal.hours_per_day) for a in acts}
    rels: list[Relationship] = []
    for r in db.query(ActivityRelationship).filter(
        ActivityRelationship.tenant_id == tenant_id, ActivityRelationship.project_id == project_id
    ):
        pred, succ = str(r.predecessor_id), str(r.successor_id)
        if pred not in by_id or succ not in by_id:
            continue
        lag = float(r.lag_hours) if r.lag_hours is not None else float(r.lag_days or 0) * hpd_of[pred]
        link = r.link_type.value if hasattr(r.link_type, "value") else str(r.link_type)
        rels.append(Relationship(task_pred_id=str(r.id), task_id=succ, pred_task_id=pred, pred_type=f"PR_{link}", lag_hr_cnt=lag))

    parsed = ParsedSchedule(
        meta=ProjectMeta(
            proj_id=str(project_id),
            proj_short_name="",
            proj_name="",
            data_date=dd,
            last_fin_date=None,
            plan_start_date=None,
            clndr_id=default_clndr,
        ),
        wbs_nodes=[],
        calendars=parsed_cals,
        activities=acts,
        relationships=rels,
    )
    return SimSource(
        parsed=parsed,
        rows=by_id,
        task_id_of={a.task_code: a.task_id for a in acts},
        cals=cals,
        default_clndr=default_clndr,
        data_date=dd,
        current_import=current,
        excluded_summary=len(all_rows) - len(rows),
        wbs_names=wbs_names(db, tenant_id, project_id),
        warnings=warnings,
    )


def wbs_names(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, str]:
    """Activity.wbs_path holds P6's wbs_id; this is what to show for it."""
    nodes = db.query(WbsNode).filter(WbsNode.tenant_id == tenant_id, WbsNode.project_id == project_id)
    return {n.wbs_id: (n.wbs_name or n.wbs_short_name) for n in nodes}


# --- runs ------------------------------------------------------------------------


def _run(src: SimSource, dd: datetime, prepare=None) -> dict[str, EngineActivity]:
    """Schedule a copy of the programme at `dd`. The relationships and
    calendars are shared (the engine only reads them); the activities are
    copied, since the engine writes its results onto them."""
    parsed = replace(
        src.parsed,
        meta=replace(src.parsed.meta, data_date=dd),
        activities=[copy.copy(a) for a in src.parsed.activities],
    )
    acts = {a.task_id: a for a in parsed.activities}
    if prepare is not None:
        prepare(acts)
    try:
        schedule(parsed, retained_logic=True)
    except CpmCycleError as e:
        raise SimulationError(
            "logic_cycle", "The programme's logic has a loop, so it can't be scheduled. Fix it in P6 and re-import."
        ) from e
    except NoWorkingDayError as e:
        raise SimulationError("calendar", str(e)) from e
    return acts


def simulation_datetime(src: SimSource, sim_date: Optional[date]) -> datetime:
    """The simulation data date as a moment: the current data date's time of
    day on the chosen day (the current data date itself when it's the same day)."""
    if sim_date is None or sim_date == src.data_date.date():
        return src.data_date
    if sim_date < src.data_date.date():
        raise SimulationError(
            "data_date_before_current",
            f"The simulation data date can't be before the current data date ({p6_date(src.data_date)}).",
        )
    return datetime.combine(sim_date, src.data_date.time())


def _progress_summary(edit: SimEdit, act: EngineActivity, is_milestone: bool, sim_dd: datetime) -> str:
    parts = []
    status = edit.status or _STATUS_OF_CODE.get(act.status_code)
    if status == "complete":
        on = edit.actual_finish or edit.actual_start or sim_dd
        parts.append(f"{'Achieved' if is_milestone else 'Completed'} on {p6_date(on)}")
    elif status == "in_progress":
        parts.append(f"In progress since {p6_date(edit.actual_start)}" if edit.actual_start else "In progress")
        if edit.percent_complete is not None:
            parts.append(f"{edit.percent_complete:g}%")
        if edit.remaining_days is not None:
            parts.append(f"{_fmt_days(edit.remaining_days)} remaining")
    else:
        parts.append("Not started")
        if edit.remaining_days is not None:
            parts.append(f"{_fmt_days(edit.remaining_days)} duration")
    if edit.expected_finish is not None:
        parts.append(f"{'moved to' if is_milestone else 'expected finish'} {p6_date(edit.expected_finish)}")
    if edit.finish_delay_days:
        d = edit.finish_delay_days
        parts.append(f"{'+' if d > 0 else '−'}{_fmt_days(abs(d))} later")
    return ", ".join(parts)


def _edit_summary(edit: SimEdit, is_milestone: bool, sim_dd: datetime, act: Optional[EngineActivity] = None) -> str:
    if edit.kind == "progress" and act is not None:
        return _progress_summary(edit, act, is_milestone, sim_dd)
    if edit.kind == "complete":
        on = edit.value or sim_dd  # no date: at the simulation data date
        return f"{'Achieved' if is_milestone else 'Marked complete'} on {p6_date(on)}"  # type: ignore[arg-type]
    if edit.kind == "actual_start":
        return f"Started on {p6_date(edit.value)}"  # type: ignore[arg-type]
    if edit.kind == "percent_complete":
        return f"Set to {float(edit.value or 0):g}% complete"
    if edit.kind == "remaining_duration":
        return f"Remaining duration set to {_fmt_days(float(edit.value or 0))}"
    if edit.kind == "finish_delay":
        days = float(edit.value or 0)
        sign = "+" if days >= 0 else "−"
        return f"{'Moved' if is_milestone else 'Finish moved'} by {sign}{_fmt_days(abs(days))}"
    return f"{'Moved to' if is_milestone else 'Finish on'} {p6_date(edit.value)}"  # type: ignore[arg-type]


def _progress_error(e: SimEdit, act: EngineActivity, milestone: bool, sim_dd: datetime) -> Optional[str]:
    sim_day = sim_dd.date()
    status = e.status or _STATUS_OF_CODE.get(act.status_code)
    if status not in ("not_started", "in_progress", "complete"):
        return "Pick a status."
    if milestone and status == "in_progress":
        return "A milestone is never in progress: it's achieved on its one date, or not yet."
    for d in (e.actual_start, e.actual_finish):
        if d is not None and d > sim_day:
            return f"Actual dates can't be after the simulation data date ({p6_date(sim_dd)})."
    if not milestone and e.actual_start and e.actual_finish and e.actual_finish < e.actual_start:
        return "Actual Finish is before Actual Start."
    if e.percent_complete is not None and not 0 <= e.percent_complete <= 100:
        return "% complete must be between 0 and 100."
    if status == "in_progress" and e.percent_complete is not None and e.percent_complete >= 100:
        return "100% is complete: set the status to Completed."
    if e.remaining_days is not None and e.remaining_days < 0:
        return "Remaining duration can't be negative."
    if status != "complete" and e.expected_finish is not None and e.expected_finish <= sim_day:
        return "Pick an expected finish after the simulation data date."
    if milestone and e.finish_delay_days is not None and e.finish_delay_days < 0:
        return "Move a milestone later only; its logic sets how early it can be."
    return None


def _validate(src: SimSource, edits: list[SimEdit], sim_dd: datetime) -> None:
    errors: list[dict] = []
    seen: set[str] = set()
    base = {a.task_id: a for a in src.parsed.activities}
    if len(edits) > MAX_EDITS:
        raise SimulationError("invalid_edits", f"A scenario can hold at most {MAX_EDITS} changes.")

    def err(e: SimEdit, message: str) -> None:
        errors.append({"external_id": e.external_id, "message": message})

    for e in edits:
        tid = src.task_id_of.get(e.external_id)
        if tid is None:
            err(e, "This activity isn't in the current programme (or is a summary / level-of-effort activity).")
            continue
        if e.external_id in seen:
            err(e, "This activity is in the scenario twice.")
            continue
        seen.add(e.external_id)
        act = base[tid]
        if e.kind not in EDIT_KINDS:
            err(e, f"Unknown change type {e.kind!r}.")
            continue
        milestone = act.task_type in MILESTONE_TYPES
        sim_day = sim_dd.date()
        if e.kind == "progress":
            message = _progress_error(e, act, milestone, sim_dd)
            if message:
                err(e, message)
            continue
        if act.status_code == "TK_Complete":
            err(e, "This activity is already complete in the live schedule.")
            continue
        if milestone and e.kind not in MILESTONE_EDIT_KINDS:
            err(e, "A milestone has one date: mark it achieved, or move it.")
            continue
        if e.kind in ("complete", "actual_start", "finish_on"):
            if e.value is not None and not isinstance(e.value, date):
                err(e, "Pick a date.")
                continue
        else:
            if e.value is None or isinstance(e.value, date):
                err(e, "Enter a number.")
                continue
        if e.kind == "complete":
            finish = e.value or sim_day
            if finish > sim_day:  # type: ignore[operator]
                err(e, f"Actual dates can't be after the simulation data date ({p6_date(sim_dd)}).")
            elif e.actual_start is not None and e.actual_start > finish:  # type: ignore[operator]
                err(e, "The finish can't be before the start.")
        elif e.kind == "actual_start":
            if e.value is None or e.value > sim_day:  # type: ignore[operator]
                err(e, f"Actual dates can't be after the simulation data date ({p6_date(sim_dd)}).")
        elif e.kind == "percent_complete":
            if not 0 <= float(e.value) <= 100:  # type: ignore[arg-type]
                err(e, "% complete must be between 0 and 100.")
        elif e.kind == "remaining_duration":
            if float(e.value) < 0:  # type: ignore[arg-type]
                err(e, "Remaining duration can't be negative.")
        elif e.kind == "finish_delay":
            if milestone and float(e.value) <= 0:  # type: ignore[arg-type]
                err(e, "Move a milestone by a positive number of days; its logic sets how early it can be.")
        elif e.kind == "finish_on":
            if e.value is None or e.value <= sim_day:  # type: ignore[operator]
                err(e, "Pick a date after the simulation data date; use Mark complete for finished work.")
    if errors:
        raise SimulationError("invalid_edits", "Some changes can't be simulated.", errors)


def _set_floor(act: EngineActivity, at: datetime) -> None:
    """A milestone held no earlier than `at` — a start/finish "on or after"
    constraint, in whichever constraint slot is free (the secondary otherwise)."""
    ctype = "CS_MSOA" if act.task_type == START_MILESTONE else "CS_MEOA"
    if not act.cstr_type:
        act.cstr_type, act.cstr_date = ctype, at
    else:
        act.cstr_type2, act.cstr_date2 = ctype, at


def _apply_progress(act: EngineActivity, e: SimEdit, cal: CalendarEngine, hpd: float, milestone: bool,
                    sim_dd: datetime, ref: EngineActivity) -> None:
    """An activity edited as in Project Activities: the status picks which of
    the dates count (routes/activities.py::_derive_status), % sets the
    remaining duration unless a remaining duration is given
    (activity_progress.apply_progress_entry), and an Expected Finish or a
    delay then stretches what's left."""
    status = e.status or _STATUS_OF_CODE[act.status_code]
    if status == "complete":
        if milestone:
            day = e.actual_finish or e.actual_start
            act_end = min(_work_end(cal, day), sim_dd) if day else sim_dd
            act_start = act_end
        else:
            act_end = min(_work_end(cal, e.actual_finish), sim_dd) if e.actual_finish else sim_dd
            if e.actual_start is not None:
                act_start = min(_work_start(cal, e.actual_start), act_end)
            elif act.act_start_date is not None:
                act_start = min(act.act_start_date, act_end)
            else:
                act_start = min(ref.early_start_date or act_end, act_end)
        act.act_start_date, act.act_end_date = act_start, act_end
        act.status_code = "TK_Complete"
        act.remain_drtn_hr_cnt = 0.0
        act.phys_complete_pct = 100.0
        act.expect_end_date = None
        return

    was_complete = act.status_code == "TK_Complete"
    act.act_end_date = None
    if status == "in_progress":
        if e.actual_start is not None:
            act.act_start_date = min(_work_start(cal, e.actual_start), sim_dd)
        elif act.act_start_date is None:
            act.act_start_date = sim_dd
        act.status_code = "TK_Active"
    else:
        act.act_start_date = None
        act.status_code = "TK_NotStart"

    target = act.target_drtn_hr_cnt or 0.0
    if e.remaining_days is not None:
        act.remain_drtn_hr_cnt = e.remaining_days * hpd
    elif e.percent_complete is not None and status == "in_progress":
        act.remain_drtn_hr_cnt = round(target * (1 - e.percent_complete / 100), 4)
    elif status == "not_started" and (was_complete or act.remain_drtn_hr_cnt <= 0):
        act.remain_drtn_hr_cnt = target
    elif was_complete:
        act.remain_drtn_hr_cnt = target
    if e.percent_complete is not None:
        act.phys_complete_pct = e.percent_complete
    elif status == "not_started":
        act.phys_complete_pct = 0.0

    if milestone:
        if e.expected_finish is not None:
            _set_floor(act, _work_start(cal, e.expected_finish) if act.task_type == START_MILESTONE else _work_end(cal, e.expected_finish))
        elif e.finish_delay_days:
            at = (ref.early_start_date if act.task_type == START_MILESTONE else ref.early_end_date) or sim_dd
            _set_floor(act, cal.add_work_hours(at, e.finish_delay_days * hpd))
        return
    if e.expected_finish is not None:
        act.expect_end_date = _work_end(cal, e.expected_finish)
    elif e.finish_delay_days:
        act.remain_drtn_hr_cnt = max(0.0, act.remain_drtn_hr_cnt + e.finish_delay_days * hpd)


def _apply(src: SimSource, acts: dict[str, EngineActivity], edits: list[SimEdit], sim_dd: datetime,
           unchanged: dict[str, EngineActivity]) -> None:
    """The progress rules of services/activity_progress.py, on the engine copy."""
    for e in edits:
        act = acts[src.task_id_of[e.external_id]]
        cal = src.cal(act)
        hpd = src.hpd(act)
        milestone = act.task_type in MILESTONE_TYPES
        if e.kind == "progress":
            _apply_progress(act, e, cal, hpd, milestone, sim_dd, unchanged[act.task_id])
        elif e.kind == "complete":
            finish_day: date = e.value or sim_dd.date()  # type: ignore[assignment]
            act_end = min(_work_end(cal, finish_day), sim_dd)
            if milestone:
                act_start = act_end
            elif act.act_start_date is not None and e.actual_start is None:
                act_start = act.act_start_date
            elif e.actual_start is not None:
                act_start = min(_work_start(cal, e.actual_start), act_end)
            else:
                planned = unchanged[act.task_id].early_start_date or act_end
                act_start = min(planned, act_end)
            act.act_start_date, act.act_end_date = min(act_start, act_end), act_end
            act.status_code = "TK_Complete"
            act.remain_drtn_hr_cnt = 0.0
            act.phys_complete_pct = 100.0
        elif e.kind == "actual_start":
            act.act_start_date = min(_work_start(cal, e.value), sim_dd)  # type: ignore[arg-type]
            act.status_code = "TK_Active"
        elif e.kind == "percent_complete":
            pct = float(e.value)  # type: ignore[arg-type]
            if pct >= 100:
                act.act_start_date = act.act_start_date or sim_dd
                act.act_end_date = sim_dd
                act.status_code = "TK_Complete"
                act.remain_drtn_hr_cnt = 0.0
            else:
                if act.status_code == "TK_NotStart":
                    act.act_start_date = sim_dd
                    act.status_code = "TK_Active"
                act.remain_drtn_hr_cnt = round((act.target_drtn_hr_cnt or 0.0) * (1 - pct / 100), 4)
            act.phys_complete_pct = pct
        elif e.kind == "remaining_duration":
            act.remain_drtn_hr_cnt = float(e.value) * hpd  # type: ignore[arg-type]
        elif e.kind == "finish_delay":
            hours = float(e.value) * hpd  # type: ignore[arg-type]
            if milestone:
                ref = unchanged[act.task_id]
                at = (ref.early_start_date if act.task_type == START_MILESTONE else ref.early_end_date) or sim_dd
                _set_floor(act, cal.add_work_hours(at, hours))
            else:
                act.remain_drtn_hr_cnt = max(0.0, (act.remain_drtn_hr_cnt or 0.0) + hours)
        elif e.kind == "finish_on":
            day: date = e.value  # type: ignore[assignment]
            if milestone:
                _set_floor(act, _work_start(cal, day) if act.task_type == START_MILESTONE else _work_end(cal, day))
            else:
                act.expect_end_date = _work_end(cal, day)


# --- comparison ------------------------------------------------------------------


def _display_start(src: SimSource, a: EngineActivity) -> Optional[datetime]:
    if a.task_type == FINISH_MILESTONE:
        return None
    dt = a.early_start_date if a.status_code == "TK_NotStart" else a.act_start_date or a.early_start_date
    if dt is None:
        return None
    cal = src.cal(a)
    # P6 shows a start that falls at the end of a working day as the next work start.
    if a.status_code == "TK_NotStart" and cal._hours_remaining_from(dt) <= 0:
        dt = cal.snap_to_work_start(datetime.combine(dt.date() + timedelta(days=1), time(0, 0)))
    return dt


def _display_finish(a: EngineActivity) -> Optional[datetime]:
    if a.task_type == START_MILESTONE:
        return None
    return a.act_end_date if a.status_code == "TK_Complete" else a.early_end_date


def _moment(a: EngineActivity) -> Optional[datetime]:
    """The one date a move is measured on: the finish (a start milestone's start)."""
    return a.early_start_date if a.task_type == START_MILESTONE else (_display_finish(a) or a.early_end_date)


def _delta_days(src: SimSource, a: EngineActivity, old: Optional[datetime], new: Optional[datetime]) -> Optional[float]:
    if old is None or new is None:
        return None
    return round(src.cal(a).work_hours_between(old, new) / src.hpd(a), 2)


def _tf_days(src: SimSource, a: EngineActivity) -> Optional[float]:
    if a.status_code == "TK_Complete" or a.total_float_hr_cnt is None:
        return None
    return round(a.total_float_hr_cnt / src.hpd(a), 2)


def _critical(a: EngineActivity) -> bool:
    return a.status_code != "TK_Complete" and a.total_float_hr_cnt is not None and a.total_float_hr_cnt <= _TOL


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.date().isoformat() if dt else None


def _causes(edited: set[str], members: set[str], acts: dict[str, EngineActivity]) -> dict[str, tuple[str, str, float]]:
    """For every member reachable from an edited activity along `acts`' driving
    links (without leaving `members`): (the step before it, link type, lag)."""
    succ_of: dict[str, list[tuple[str, str, float]]] = {}
    for tid in members:
        for pred, rtype, lag in acts[tid].driving_rels:
            if pred in members:
                succ_of.setdefault(pred, []).append((tid, rtype, lag))
    parent: dict[str, tuple[str, str, float]] = {}
    queue = deque(sorted(edited & members))
    seen = set(queue)
    while queue:
        tid = queue.popleft()
        for succ, rtype, lag in succ_of.get(tid, []):
            if succ not in seen:
                seen.add(succ)
                parent[succ] = (tid, rtype, lag)
                queue.append(succ)
    return parent


def _project_finish(acts: dict[str, EngineActivity]) -> tuple[Optional[EngineActivity], Optional[datetime]]:
    dated = [a for a in acts.values() if a.early_end_date is not None]
    if not dated:
        return None, None
    # Ties go to an unfinished milestone (the completion milestone), then the ID.
    best = max(
        dated, key=lambda a: (a.early_end_date, a.status_code != "TK_Complete", a.task_type in MILESTONE_TYPES, a.task_code)
    )
    return best, best.early_end_date


def run_simulation(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, sim_date: Optional[date],
                   edits: list[SimEdit]) -> dict:
    src = build_sim_source(db, tenant_id, project_id)
    sim_dd = simulation_datetime(src, sim_date)
    _validate(src, edits, sim_dd)

    current = _run(src, src.data_date)
    unchanged = current if sim_dd == src.data_date else _run(src, sim_dd)
    simulated = _run(src, sim_dd, lambda acts: _apply(src, acts, edits, sim_dd, unchanged))

    edit_of = {src.task_id_of[e.external_id]: e for e in edits}
    edited = set(edit_of)
    project_cal = src.cals[src.default_clndr or ""]
    project_hpd = valid_hours_per_day(project_cal._cal.hours_per_day)

    def finish_delta(a_dt: Optional[datetime], b_dt: Optional[datetime]) -> float:
        if a_dt is None or b_dt is None:
            return 0.0
        return round(project_cal.work_hours_between(a_dt, b_dt) / project_hpd, 2)

    # --- what moved (simulated vs unchanged) ---
    moved_ids: list[str] = []
    for tid, after in simulated.items():
        before = unchanged[tid]
        dates_moved = any(
            x is not None and y is not None and abs(src.cal(after).work_hours_between(x, y)) > _TOL
            for x, y in ((before.early_start_date, after.early_start_date), (before.early_end_date, after.early_end_date),
                         (_display_start(src, before), _display_start(src, after)))
        )
        if tid in edited or dates_moved or _critical(before) != _critical(after):
            moved_ids.append(tid)
    members = set(moved_ids)

    later_cause = _causes(edited, members, simulated)
    earlier_cause = _causes(edited, members, unchanged)

    def driver_of(tid: str, cause: Optional[tuple[str, str, float]]) -> dict:
        a = simulated[tid]
        if tid in edited:
            return {"kind": "edit", "summary": _edit_summary(edit_of[tid], a.task_type in MILESTONE_TYPES, sim_dd, a)}
        if a.driven_by == "logic" and a.driving_rels:
            rel = next((r for r in a.driving_rels if cause and r[0] == cause[0]), a.driving_rels[0])
            pred = simulated[rel[0]]
            return {
                "kind": "predecessor",
                "external_id": pred.task_code,
                "name": pred.task_name,
                "link_type": _LINK_OF_TYPE.get(rel[1], "FS"),
                "lag_days": round(rel[2] / src.hpd(pred), 2),
            }
        if a.driven_by == "constraint":
            ctype = a.cstr_type if a.cstr_type in _CONSTRAINT_LABELS else a.cstr_type2
            cdate = a.cstr_date if ctype == a.cstr_type else a.cstr_date2
            return {"kind": "constraint", "label": _CONSTRAINT_LABELS.get(ctype or "", "Constraint"), "date": _iso(cdate)}
        if a.driven_by == "actual":
            return {"kind": "actual"}
        return {"kind": "data_date"}

    def row(tid: str) -> dict:
        before, after = unchanged[tid], simulated[tid]
        db_row = src.rows[tid]
        sb, sa_ = _display_start(src, before), _display_start(src, after)
        fb, fa = _display_finish(before), _display_finish(after)
        delta = _delta_days(src, after, _moment(before), _moment(after)) or 0.0
        start_delta = _delta_days(src, after, sb, sa_)
        if abs(delta) < 0.005:
            direction = "later" if (start_delta or 0) > 0.005 else "earlier" if (start_delta or 0) < -0.005 else "same"
        else:
            direction = "later" if delta > 0 else "earlier"
        cause = (earlier_cause if direction == "earlier" else later_cause).get(tid)
        return {
            "id": tid,
            "external_id": after.task_code,
            "name": after.task_name,
            "wbs_name": src.wbs_names.get(db_row.wbs_path or "") or db_row.wbs_path,
            "task_type": after.task_type,
            "hours_per_day": src.hpd(after),
            "status_before": _STATUS_OF_CODE[before.status_code],
            "status_after": _STATUS_OF_CODE[after.status_code],
            "start_before": _iso(sb),
            "start_after": _iso(sa_),
            "finish_before": _iso(fb),
            "finish_after": _iso(fa),
            "start_delta_days": start_delta,
            "finish_delta_days": delta,
            "direction": direction,
            "total_float_before_days": _tf_days(src, before),
            "total_float_after_days": _tf_days(src, after),
            "critical_before": _critical(before),
            "critical_after": _critical(after),
            "longest_path_after": bool(after.lp_critical) and after.status_code != "TK_Complete",
            "is_edited": tid in edited,
            "driver": driver_of(tid, cause),
            "cause": (
                {
                    "external_id": simulated[cause[0]].task_code,
                    "link_type": _LINK_OF_TYPE.get(cause[1], "FS"),
                    "lag_days": round(cause[2] / src.hpd(simulated[cause[0]]), 2),
                }
                if cause
                else None
            ),
        }

    rows = [row(tid) for tid in moved_ids]
    rows.sort(key=lambda r: (not r["is_edited"], -abs(r["finish_delta_days"] or 0), r["finish_after"] or "", r["external_id"]))
    truncated = len(rows) > MAX_ROWS

    # --- milestones: every unfinished one (plus any changed) ---
    milestone_rows = []
    for tid, after in simulated.items():
        if after.task_type not in MILESTONE_TYPES:
            continue
        if unchanged[tid].status_code == "TK_Complete" and tid not in edited:
            continue
        milestone_rows.append(row(tid))

    # --- headline ---
    fin_act, fin_sim = _project_finish(simulated)
    _, fin_unchanged = _project_finish(unchanged)
    _, fin_current = _project_finish(current)
    for m in milestone_rows:
        m["is_project_finish"] = fin_act is not None and m["id"] == fin_act.task_id

    warnings = list(src.warnings)
    for e in edits:
        tid = src.task_id_of[e.external_id]
        a = simulated[tid]
        if a.status_code in ("TK_Active", "TK_Complete"):
            for rel in src.parsed.relationships:
                if rel.task_id != tid or rel.pred_type not in ("PR_FS",):
                    continue
                pred = simulated.get(rel.pred_task_id)
                if pred is not None and pred.status_code != "TK_Complete":
                    warnings.append(
                        {
                            "code": "out_of_sequence",
                            "external_id": a.task_code,
                            "message": f"{a.task_code} has progress while its predecessor {pred.task_code} is "
                            "unfinished; under Retained Logic its remaining work waits for it.",
                        }
                    )
                    break
        moves_milestone = e.kind in ("finish_on", "finish_delay") or (
            e.kind == "progress" and (e.expected_finish is not None or bool(e.finish_delay_days))
        )
        if moves_milestone and a.task_type in MILESTONE_TYPES and a.status_code != "TK_Complete":
            wanted = a.cstr_date2 if a.cstr_type2 in ("CS_MSOA", "CS_MEOA") and a.cstr_date2 else a.cstr_date
            got = _moment(a)
            if wanted and got and abs(src.cal(a).work_hours_between(wanted, got)) > _TOL:
                warnings.append(
                    {
                        "code": "edit_overridden",
                        "external_id": a.task_code,
                        "message": f"{a.task_code} can't be on {p6_date(wanted)}: its logic holds it to {p6_date(got)}.",
                    }
                )

    data_date_moved = 0
    if unchanged is not current:
        for tid, a in unchanged.items():
            b = current[tid]
            if a.early_end_date and b.early_end_date and abs(src.cal(a).work_hours_between(b.early_end_date, a.early_end_date)) > _TOL:
                data_date_moved += 1

    crit_before = {tid for tid, a in unchanged.items() if _critical(a)}
    crit_after = {tid for tid, a in simulated.items() if _critical(a)}
    later = sum(1 for r in rows if r["direction"] == "later")
    earlier = sum(1 for r in rows if r["direction"] == "earlier")
    imp = src.current_import
    return {
        "run_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "import_id": str(imp.id),
        "revision_label": imp.revision_label,
        "current_data_date": src.data_date.date().isoformat(),
        "simulation_data_date": sim_dd.date().isoformat(),
        "total_activities": len(simulated),
        "excluded_summary": src.excluded_summary,
        "project_finish": {
            "external_id": fin_act.task_code if fin_act else None,
            "name": fin_act.task_name if fin_act else None,
            "current": _iso(fin_current),
            "unchanged": _iso(fin_unchanged),
            "simulated": _iso(fin_sim),
            "delta_days": finish_delta(fin_unchanged, fin_sim),
            "data_date_delta_days": finish_delta(fin_current, fin_unchanged),
            "total_delta_days": finish_delta(fin_current, fin_sim),
        },
        "counts": {
            "moved": later + earlier,
            "later": later,
            "earlier": earlier,
            "milestones_moved": sum(1 for m in milestone_rows if m["direction"] != "same"),
            "milestones_total": len(milestone_rows),
            "critical_before": len(crit_before),
            "critical_after": len(crit_after),
            "joined_critical": len(crit_after - crit_before),
            "left_critical": len(crit_before - crit_after),
            "data_date_moved": data_date_moved,
        },
        "moved": rows[:MAX_ROWS],
        "truncated": truncated,
        "milestones": milestone_rows,
        "warnings": warnings,
    }


# --- what the page's activity picker lists ------------------------------------


def picker_activities(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> list[dict]:
    """The current programme's activities as the live schedule shows them
    (P6's stored dates and float) — the "Now" the scenario starts from."""
    out = []
    names = wbs_names(db, tenant_id, project_id)
    for a in current_programme_activities(db, tenant_id, project_id):
        if (a.task_type or "") in _SUMMARY_TYPES:
            continue
        hpd = valid_hours_per_day(a.hours_per_day)
        milestone = a.task_type in MILESTONE_TYPES
        if a.task_type == FINISH_MILESTONE:
            start = None
        else:
            start = (a.early_start or a.planned_start) if a.status == ActivityStatus.not_started else a.actual_start
        if a.task_type == START_MILESTONE:
            finish = None
        else:
            finish = a.actual_finish if a.status == ActivityStatus.complete else (a.early_finish or a.planned_finish)
        if a.remaining_duration_hours is not None:
            remaining = a.remaining_duration_hours / hpd
        else:
            remaining = float(a.remaining_duration_days or 0)
        out.append(
            {
                "id": str(a.id),
                "external_id": a.external_id,
                "name": a.name,
                "wbs_name": names.get(a.wbs_path or "") or a.wbs_path,
                "task_type": a.task_type,
                "is_milestone": milestone,
                "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                "start": start.isoformat() if start else None,
                "finish": finish.isoformat() if finish else None,
                "total_float_days": None if a.total_float_hours is None else round(a.total_float_hours / hpd, 2),
                "remaining_days": round(remaining, 2),
                "original_days": None if a.target_duration_hours is None else round(a.target_duration_hours / hpd, 2),
                "percent_complete": a.percent_complete,
                "hours_per_day": hpd,
            }
        )
    return out
