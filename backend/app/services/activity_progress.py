"""What else moves when an activity's progress changes in Poko.

Things P6 would derive itself, and that the user reads in Poko before the file
ever goes back to P6:

  - A finished activity has no float: its total and free float are zero and it
    is never critical (P6's own convention, and what the importer's
    `_is_critical` already assumes).
  - Its RT_Labor assignments' units follow the entered %:
    act_reg_qty = target_qty x %, remain_qty = target_qty - act_reg_qty
    (their sum is TASK.act_work_qty on export). Material / equipment units and
    all costs are left alone — costs are the AC side of EVM, and deriving them
    from % would make actual cost equal earned value by construction.
  - An activity without labor resources records the entered % as its physical
    % (TASK.phys_complete_pct) and moves its remaining duration to match:
    remain_drtn = target_drtn x (1 - %), so the duration % Poko shows for it
    equals what was entered and the file P6 gets back says the same.

What Poko shows as % (`Activity.percent_complete`) — `display_percent`:

  - labor resources assigned: act_reg_qty / target_qty (summed over them);
  - otherwise Completed 100, Not Started 0, In Progress the duration %
    (target_drtn - remain_drtn) / target_drtn — or, with no duration to go
    by, the physical %; failing all of that, 0.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.engine.durations import activity_hours_per_day
from app.models.activity import Activity, ActivityStatus
from app.models.resource_assignment import ResourceAssignment


def _clamp_pct(value: float) -> int:
    return max(0, min(100, round(value)))


def display_percent(
    status: ActivityStatus,
    target_hours: Optional[float],
    remaining_hours: Optional[float],
    labor_budget: float = 0.0,
    labor_actual: float = 0.0,
    phys_pct: Optional[float] = None,
) -> int:
    """The % Poko shows for an activity (module docstring). Plain values, so
    the importer can call it on parsed .xer rows as well as on Activity rows."""
    if labor_budget > 0:
        return _clamp_pct(labor_actual / labor_budget * 100)
    if status == ActivityStatus.complete:
        return 100
    if status == ActivityStatus.not_started:
        return 0
    if target_hours and target_hours > 0 and remaining_hours is not None:
        return _clamp_pct((target_hours - remaining_hours) / target_hours * 100)
    return _clamp_pct(phys_pct or 0)


def labor_units(labor: Iterable[ResourceAssignment]) -> tuple[float, float]:
    """(budget, actual) units over an activity's labor assignments."""
    budget = actual = 0.0
    for assignment in labor:
        budget += assignment.target_qty or 0.0
        actual += assignment.act_reg_qty or 0.0
    return budget, actual


def progress_fraction(activity: Activity) -> float:
    if activity.status == ActivityStatus.complete:
        return 1.0
    return max(0.0, min(100.0, float(activity.percent_complete or 0))) / 100.0


def apply_units_from_progress(activity: Activity, labor: Iterable[ResourceAssignment]) -> None:
    """Split each LABOR assignment's budget by the activity's %. Callers pass
    only the RT_Labor assignments."""
    fraction = progress_fraction(activity)
    for assignment in labor:
        budget = assignment.target_qty or 0.0
        assignment.act_reg_qty = round(budget * fraction, 4)
        assignment.remain_qty = round(budget - assignment.act_reg_qty, 4)


def apply_progress_entry(
    activity: Activity,
    labor: list[ResourceAssignment],
    *,
    pct_entered: bool,
    remaining_entered: bool,
    status_changed: bool,
) -> None:
    """Carry a progress edit through to units / physical % / remaining duration,
    then re-derive the displayed %. Runs after the route has settled status and
    actual dates (routes/activities.py::_apply_progress_derivation)."""
    budget, _ = labor_units(labor)
    hpd = activity_hours_per_day(activity)
    target = activity.target_duration_hours

    if activity.status == ActivityStatus.complete:
        activity.phys_complete_pct = 100.0
        activity.remaining_duration_hours = 0.0
        activity.remaining_duration_days = 0
    elif activity.status == ActivityStatus.not_started:
        activity.phys_complete_pct = 0.0
        if target is not None:
            activity.remaining_duration_hours = target
    elif budget <= 0 and pct_entered:
        pct = float(activity.percent_complete or 0)
        activity.phys_complete_pct = pct
        if target:
            activity.remaining_duration_hours = round(target * (1 - pct / 100), 4)
            activity.remaining_duration_days = round(activity.remaining_duration_hours / hpd)
    elif remaining_entered:
        activity.remaining_duration_hours = float(activity.remaining_duration_days) * hpd

    if budget > 0 and (pct_entered or status_changed):
        apply_units_from_progress(activity, labor)

    actual = labor_units(labor)[1]
    activity.percent_complete = display_percent(
        activity.status,
        target,
        activity.remaining_duration_hours,
        budget,
        actual,
        activity.phys_complete_pct,
    )


def clear_float_if_finished(activity: Activity) -> None:
    if activity.status == ActivityStatus.complete:
        activity.total_float_hours = 0.0
        activity.free_float_hours = 0.0
        activity.is_critical = False
