"""What else moves when an activity's progress changes in Poko.

Two things P6 would derive itself, and that the user reads in Poko before the
file ever goes back to P6:

  - A finished activity has no float: its total and free float are zero and it
    is never critical (P6's own convention, and what the importer's
    `_is_critical` already assumes).
  - Its resource assignments' units follow the physical %:
    actual = budget x %, remaining = budget - actual. Costs are left alone —
    they're the AC side of EVM, and deriving them from % would make actual cost
    equal earned value by construction.
"""

from __future__ import annotations

from typing import Iterable

from app.models.activity import Activity, ActivityStatus
from app.models.resource_assignment import ResourceAssignment


def progress_fraction(activity: Activity) -> float:
    if activity.status == ActivityStatus.complete:
        return 1.0
    return max(0.0, min(100.0, float(activity.percent_complete or 0))) / 100.0


def apply_units_from_progress(activity: Activity, assignments: Iterable[ResourceAssignment]) -> None:
    fraction = progress_fraction(activity)
    for assignment in assignments:
        budget = assignment.target_qty or 0.0
        assignment.act_reg_qty = round(budget * fraction, 4)
        assignment.remain_qty = round(budget - assignment.act_reg_qty, 4)


def clear_float_if_finished(activity: Activity) -> None:
    if activity.status == ActivityStatus.complete:
        activity.total_float_hours = 0.0
        activity.free_float_hours = 0.0
        activity.is_critical = False
