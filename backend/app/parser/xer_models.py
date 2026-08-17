"""Canonical in-memory shape of a parsed .xer file.

Ported from a colleague's reference P6 desktop app (`xer_models.py`), trimmed to what
CPM scheduling needs — no resource/activity-code dataclasses this slice (see
`backend/app/services/xer_import.py` for why: they don't affect float/critical-path,
and nothing in this codebase reads them yet). Deliberately plain dataclasses, not
SQLAlchemy models or Pydantic schemas: these are the CPM engine's working data
structures, built fresh from a parsed file and thrown away once
`services/xer_import.py` has written the results into Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional


@dataclass
class ProjectMeta:
    proj_id: str
    proj_short_name: str
    proj_name: str
    data_date: Optional[datetime]
    last_fin_date: Optional[datetime]  # Must Finish By
    plan_start_date: Optional[datetime]
    clndr_id: Optional[str]  # default project calendar


@dataclass
class WbsNode:
    wbs_id: str
    proj_id: str
    parent_wbs_id: Optional[str]
    wbs_short_name: str
    wbs_name: str
    seq_num: Optional[int]


@dataclass
class DayShift:
    """One continuous work period within a day."""

    start: time
    end: time


@dataclass
class CalendarDay:
    """Work periods for a specific weekday (0=Sun … 6=Sat, P6 convention)."""

    day_of_week: int
    shifts: list[DayShift]

    @property
    def total_hours(self) -> float:
        return sum(
            (s.end.hour + s.end.minute / 60) - (s.start.hour + s.start.minute / 60) for s in self.shifts
        )

    @property
    def is_working(self) -> bool:
        return len(self.shifts) > 0


@dataclass
class CalendarException:
    """A date-specific override (holiday or extra workday)."""

    exc_date: datetime
    shifts: list[DayShift]  # empty list = non-working day

    @property
    def is_working(self) -> bool:
        return len(self.shifts) > 0


@dataclass
class Calendar:
    clndr_id: str
    clndr_name: str
    default_work_week: list[CalendarDay]  # 7 entries (Sun-Sat)
    exceptions: list[CalendarException]
    hours_per_day: float = 8.0


@dataclass
class Activity:
    task_id: str
    proj_id: str
    wbs_id: Optional[str]
    clndr_id: Optional[str]
    task_code: str
    task_name: str
    task_type: str  # TT_Task, TT_Mile, TT_FinMile, TT_StartMile, TT_WBS, TT_LOE
    status_code: str  # TK_NotStart, TK_Active, TK_Complete
    phys_complete_pct: float

    # Durations (hours) — never modified by the CPM engine.
    target_drtn_hr_cnt: float
    remain_drtn_hr_cnt: float

    # Schedule dates — written by the CPM engine.
    early_start_date: Optional[datetime] = None
    early_end_date: Optional[datetime] = None
    late_start_date: Optional[datetime] = None
    late_end_date: Optional[datetime] = None

    # Actual dates — read-only for the engine.
    act_start_date: Optional[datetime] = None
    act_end_date: Optional[datetime] = None

    # Planned (baseline) dates.
    target_start_date: Optional[datetime] = None
    target_end_date: Optional[datetime] = None

    restart_date: Optional[datetime] = None
    reend_date: Optional[datetime] = None

    # Float (hours) — written by the CPM engine.
    total_float_hr_cnt: Optional[float] = None
    free_float_hr_cnt: Optional[float] = None

    # Constraints.
    cstr_type: Optional[str] = None
    cstr_date: Optional[datetime] = None
    cstr_type2: Optional[str] = None
    cstr_date2: Optional[datetime] = None

    seq_num: Optional[int] = None

    # Set by the scheduler after the float-calculation pass; not part of the raw
    # XER shape. Kept as plain attributes (not a dataclass field) exactly like the
    # reference engine, since callers only ever read them after schedule() runs.
    tf_days: Optional[float] = field(default=None, init=False, repr=False)
    ff_days: Optional[float] = field(default=None, init=False, repr=False)
    lp_critical: bool = field(default=False, init=False, repr=False)


@dataclass
class Relationship:
    task_pred_id: str
    task_id: str  # successor
    pred_task_id: str  # predecessor
    pred_type: str  # PR_FS, PR_SS, PR_FF, PR_SF
    lag_hr_cnt: float  # lag in hours (negative = lead)


@dataclass
class Resource:
    rsrc_id: str
    rsrc_name: str
    rsrc_short_name: str
    rsrc_type: str  # RT_Labor, RT_Material, RT_Equipment
    unit_id: Optional[str]
    clndr_id: Optional[str]
    curr_id: Optional[str]


@dataclass
class ResourceAssignment:
    taskrsrc_id: str
    task_id: str
    rsrc_id: str
    remain_qty: float
    target_qty: float  # budgeted quantity (hours, for RT_Labor)
    act_reg_qty: float  # actual quantity spent
    target_cost: float
    act_reg_cost: float
    remain_cost: float
    unit_id: Optional[str]


@dataclass
class ParsedSchedule:
    """Everything one `.xer` upload produces. Not persisted as-is anywhere — see
    `services/xer_import.py::import_xer` for how this becomes Postgres rows."""

    meta: ProjectMeta
    wbs_nodes: list[WbsNode]
    calendars: list[Calendar]
    activities: list[Activity]
    relationships: list[Relationship]
    resources: list[Resource] = field(default_factory=list)
    assignments: list[ResourceAssignment] = field(default_factory=list)
    parse_log: list[str] = field(default_factory=list)
