"""Quick/live EVM (Earned Value Management) — ported from the reference
project's `backend/app/engine/evm/evm_engine.py` (264 lines). Computed
on-demand from the project's CURRENT activities/resource-assignments, no
baseline needed — this is one of two EVM systems the reference project runs.
The other, baseline-locked S-curve time series, is `engine/evm/scurve_engine.py`
— it uses target_duration_hours as a manhours-effort proxy for BAC instead of
real resource quantities, so it needs no resource data at all. This engine is
the more accurate one when a project actually has resource-loaded activities.

Formulas (PMBOK / EVMS / AACE 57R-09), unchanged from the reference:
  BAC = Sum of target_qty (budgeted hours) across an activity's resource assignments
  PV  = BAC x planned_pct (calendar-aware, via CalendarEngine.work_hours_between)
  EV  = BAC x percent_complete
  AC  = Sum of act_reg_qty, unless overridden by a caller-supplied burned-hours map
  CPI = EV / AC, SPI = EV / PV, SV = EV - PV, CV = EV - AC
  EAC_cpi = BAC / CPI, EAC_pf = AC + (BAC - EV), VAC = BAC - EAC_cpi
All index/ratio metrics return None when the denominator is zero — "cannot be
calculated" rather than a misleading number.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional

from app.engine.cpm.calendar_engine import CalendarEngine
from app.models.activity import Activity
from app.models.calendar import Calendar as CalendarModel
from app.models.resource_assignment import ResourceAssignment
from app.parser.xer_models import Calendar as ParsedCalendar, CalendarDay, CalendarException, DayShift


@dataclass
class ActivityEVM:
    activity_id: uuid.UUID
    external_id: str
    name: str
    status_code: Optional[str]
    percent_complete: int

    bac: float
    pv: Optional[float]
    ev: float
    ac: float

    cpi: Optional[float]
    spi: Optional[float]
    sv: Optional[float]
    cv: float

    eac_cpi: Optional[float]
    eac_pf: Optional[float]
    vac: Optional[float]

    remaining_manhour: float
    remaining_qty: float


@dataclass
class ProjectEVM:
    data_date: Optional[datetime]

    bac: float
    pv: Optional[float]
    ev: float
    ac: float

    cpi: Optional[float]
    spi: Optional[float]
    sv: Optional[float]
    cv: float

    eac_cpi: Optional[float]
    eac_pf: Optional[float]
    vac: Optional[float]

    activity_results: list[ActivityEVM] = field(default_factory=list)


def _safe_div(num: float, den: float) -> Optional[float]:
    if den == 0:
        return None
    return round(num / den, 6)


def _as_dt(d) -> Optional[datetime]:
    return datetime(d.year, d.month, d.day) if d else None


def _parse_hhmm(s: str) -> time:
    return time(int(s[:2]), int(s[3:5]))


def build_calendar_engine(calendar_row: CalendarModel) -> CalendarEngine:
    """A CalendarEngine over a stored calendar, so we can reuse
    CalendarEngine.work_hours_between without duplicating its logic."""
    return CalendarEngine(calendar_row_to_parsed(calendar_row))


def calendar_row_to_parsed(calendar_row: CalendarModel, clndr_id: str | None = None) -> ParsedCalendar:
    """Reconstructs the parser's in-memory Calendar dataclass from our stored
    JSON (inverse of the shape `services/xer_import.py` writes). `clndr_id`
    overrides the P6 id it's keyed by."""
    week = [
        CalendarDay(
            day_of_week=d["day_of_week"],
            shifts=[DayShift(start=_parse_hhmm(s["start"]), end=_parse_hhmm(s["end"])) for s in d["shifts"]],
        )
        for d in calendar_row.work_week
    ]
    exceptions = [
        CalendarException(
            exc_date=datetime.fromisoformat(e["exc_date"]),
            shifts=[DayShift(start=_parse_hhmm(s["start"]), end=_parse_hhmm(s["end"])) for s in e["shifts"]],
        )
        for e in calendar_row.exceptions
    ]
    return ParsedCalendar(
        clndr_id=clndr_id or calendar_row.clndr_id,
        clndr_name=calendar_row.name,
        default_work_week=week,
        exceptions=exceptions,
        hours_per_day=calendar_row.hours_per_day,
    )


def _planned_pct_calendar_aware(
    activity: Activity, data_date: datetime, cal_engine: Optional[CalendarEngine]
) -> float:
    """Estimate planned progress % at data_date using calendar-aware work hours.
    Falls back to linear interpolation if no calendar is available."""
    t_start = _as_dt(activity.planned_start) or _as_dt(activity.early_start)
    t_end = _as_dt(activity.planned_finish) or _as_dt(activity.early_finish)

    if not t_start or not t_end:
        return 0.0
    if data_date <= t_start:
        return 0.0
    if data_date >= t_end:
        return 1.0

    if cal_engine is not None:
        total_work = cal_engine.work_hours_between(t_start, t_end)
        elapsed_work = cal_engine.work_hours_between(t_start, data_date)
        if total_work <= 0:
            return 1.0
        return min(max(elapsed_work / total_work, 0.0), 1.0)

    total_span = (t_end - t_start).total_seconds()
    elapsed = (data_date - t_start).total_seconds()
    if total_span <= 0:
        return 1.0
    return min(max(elapsed / total_span, 0.0), 1.0)


def _calc_activity_evm(
    activity: Activity,
    assignments: list[ResourceAssignment],
    data_date: datetime,
    cal_engine: Optional[CalendarEngine],
) -> ActivityEVM:
    bac = sum(a.target_qty for a in assignments)

    pct = activity.percent_complete / 100.0
    ev = round(bac * pct, 4)

    ac = round(sum(a.act_reg_qty for a in assignments), 4)

    planned_pct = _planned_pct_calendar_aware(activity, data_date, cal_engine)
    pv = round(bac * planned_pct, 4) if bac > 0 else 0.0

    cpi = _safe_div(ev, ac)
    spi = _safe_div(ev, pv)
    sv = round(ev - pv, 4)
    cv = round(ev - ac, 4)

    eac_cpi = _safe_div(bac, cpi) if cpi is not None else None
    eac_pf = round(ac + (bac - ev), 4)
    vac = round(bac - eac_cpi, 4) if eac_cpi is not None else None

    remaining_manhour = round(bac - ev, 4)
    remaining_qty = round(bac * (1.0 - pct), 4)

    return ActivityEVM(
        activity_id=activity.id,
        external_id=activity.external_id,
        name=activity.name,
        status_code=activity.status_code,
        percent_complete=activity.percent_complete,
        bac=bac, pv=pv, ev=ev, ac=ac,
        cpi=cpi, spi=spi, sv=sv, cv=cv,
        eac_cpi=eac_cpi, eac_pf=eac_pf, vac=vac,
        remaining_manhour=remaining_manhour,
        remaining_qty=remaining_qty,
    )


def calculate_evm(
    activities: list[Activity],
    assignments: list[ResourceAssignment],
    calendars: list[CalendarModel],
    data_date: Optional[datetime],
    burned_hours: Optional[dict[uuid.UUID, float]] = None,
) -> ProjectEVM:
    """Calculate EVM for all activities and roll up to project level.
    `burned_hours` (activity_id -> hours), when provided, overrides AC for
    that activity — same "Poko-only manual override" concept as the
    reference's burned-manhour field."""
    dd = data_date or datetime.utcnow()
    burned = burned_hours or {}

    cal_by_id = {c.id: c for c in calendars}
    default_cal_row = calendars[0] if calendars else None
    engine_cache: dict[uuid.UUID, CalendarEngine] = {}

    def get_cal(clndr_row_id: Optional[uuid.UUID]) -> Optional[CalendarEngine]:
        row = cal_by_id.get(clndr_row_id) or default_cal_row
        if row is None:
            return None
        if row.id not in engine_cache:
            engine_cache[row.id] = build_calendar_engine(row)
        return engine_cache[row.id]

    assign_map: dict[uuid.UUID, list[ResourceAssignment]] = {}
    for a in assignments:
        assign_map.setdefault(a.activity_id, []).append(a)

    activity_results: list[ActivityEVM] = []
    for act in activities:
        cal_engine = get_cal(act.clndr_id)
        act_assignments = assign_map.get(act.id, [])
        result = _calc_activity_evm(act, act_assignments, dd, cal_engine)
        if act.id in burned:
            result.ac = round(float(burned[act.id]), 4)
            result.cv = round(result.ev - result.ac, 4)
            result.cpi = _safe_div(result.ev, result.ac)
            result.eac_cpi = _safe_div(result.bac, result.cpi) if result.cpi else None
            result.vac = round(result.bac - result.eac_cpi, 4) if result.eac_cpi else None
        activity_results.append(result)

    total_bac = sum(r.bac for r in activity_results)
    total_ev = sum(r.ev for r in activity_results)
    total_ac = sum(r.ac for r in activity_results)
    total_pv = sum(r.pv for r in activity_results if r.pv is not None)

    cpi = _safe_div(total_ev, total_ac)
    spi = _safe_div(total_ev, total_pv)
    sv = round(total_ev - total_pv, 4)
    cv = round(total_ev - total_ac, 4)

    eac_cpi = _safe_div(total_bac, cpi) if cpi is not None else None
    eac_pf = round(total_ac + (total_bac - total_ev), 4)
    vac = round(total_bac - eac_cpi, 4) if eac_cpi is not None else None

    return ProjectEVM(
        data_date=dd,
        bac=round(total_bac, 4), pv=round(total_pv, 4), ev=round(total_ev, 4), ac=round(total_ac, 4),
        cpi=cpi, spi=spi, sv=sv, cv=cv,
        eac_cpi=eac_cpi, eac_pf=eac_pf, vac=vac,
        activity_results=activity_results,
    )
