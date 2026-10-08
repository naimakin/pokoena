"""What else moves when an activity's progress changes in Poko.

Things P6 would derive itself, and that the user reads in Poko before the file
ever goes back to P6:

  - A finished activity has no float: its total and free float are blank (as
    P6 writes them) and it is never critical (P6's own convention, and what the importer's
    `_is_critical` already assumes).
  - Every resource assignment's units follow the entered % — labor
    (RT_Labor), nonlabor (RT_Equip) and material (RT_Mat) alike:
    act_reg_qty = target_qty x %, remain_qty = target_qty - act_reg_qty.
    On export the labor ones roll up into TASK.act_work_qty and the nonlabor
    ones into TASK.act_equip_qty; P6 has no activity-level material total.
    Costs are left alone — they are the AC side of EVM, and deriving them
    from % would make actual cost equal earned value by construction.
  - The entered % is also the physical % (TASK.phys_complete_pct), and the
    remaining duration moves to match: remain_drtn = target_drtn x (1 - %).
    P6 shows an activity's % by its complete_pct_type — physical, duration or
    units — so with all three moved together P6 opens the file showing the %
    that was entered, whichever the activity uses; and the duration % Poko
    shows for an activity without labor equals it too.

What Poko shows as % (`Activity.percent_complete`) — `display_percent`:

  - labor resources assigned: act_reg_qty / target_qty (summed over the
    labor ones — nonlabor and material units are in their own unit of measure,
    so they don't enter the %);
  - otherwise Completed 100, Not Started 0, In Progress the duration %
    (target_drtn - remain_drtn) / target_drtn — or, with no duration to go
    by, the physical %; failing all of that, 0.
"""

from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.durations import activity_hours_per_day
from app.models.activity import Activity, ActivityStatus
from app.models.resource import LABOR, Resource
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


def annotate_labor_units(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, activities: list[Activity]
) -> None:
    """Attach each activity's RT_Labor (budget, actual) hours as transient
    `labor_budget_hours` / `labor_actual_hours` — the grids roll them up into a
    units % over whatever set is filtered (sum actual / sum budget, as P6's
    Units % Complete column does on a WBS band)."""
    if not activities:
        return
    rows = (
        db.query(
            ResourceAssignment.activity_id,
            func.coalesce(func.sum(ResourceAssignment.target_qty), 0.0),
            func.coalesce(func.sum(ResourceAssignment.act_reg_qty), 0.0),
        )
        .join(Resource, Resource.id == ResourceAssignment.resource_id)
        .filter(
            ResourceAssignment.tenant_id == tenant_id,
            ResourceAssignment.project_id == project_id,
            Resource.rsrc_type == LABOR,
        )
        .group_by(ResourceAssignment.activity_id)
        .all()
    )
    units = {activity_id: (float(budget), float(actual)) for activity_id, budget, actual in rows}
    for activity in activities:
        activity.labor_budget_hours, activity.labor_actual_hours = units.get(activity.id, (0.0, 0.0))


def snapshot_labor_units(assignments_snapshot: list[dict]) -> dict[str, tuple[float, float]]:
    """(budget, actual) RT_Labor hours per external_id from an import's frozen
    assignments_snapshot — the same numbers annotate_labor_units gives live rows."""
    units: dict[str, tuple[float, float]] = {}
    for row in assignments_snapshot:
        if row.get("rsrc_type") != LABOR:
            continue
        budget, actual = units.get(row["external_id"], (0.0, 0.0))
        units[row["external_id"]] = (budget + (row.get("budget") or 0.0), actual + (row.get("actual") or 0.0))
    return units


def progress_fraction(activity: Activity) -> float:
    if activity.status == ActivityStatus.complete:
        return 1.0
    return max(0.0, min(100.0, float(activity.percent_complete or 0))) / 100.0


def apply_units_from_progress(activity: Activity, assignments: Iterable[ResourceAssignment]) -> None:
    """Split each assignment's budget by the activity's %, whatever its
    resource type."""
    fraction = progress_fraction(activity)
    for assignment in assignments:
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
    nonlabor: list[ResourceAssignment] | None = None,
) -> None:
    """Carry a progress edit through to units / physical % / remaining duration,
    then re-derive the displayed %. Runs after the route has settled status and
    actual dates (routes/activities.py::_apply_progress_derivation).

    `labor` are the RT_Labor assignments (they also drive the displayed %),
    `nonlabor` every other one (RT_Equip, RT_Mat) — units follow the % on both."""
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
    elif pct_entered:
        # Every measure P6 can show a % by (TASK.complete_pct_type: CP_Phys,
        # CP_Drtn, CP_Units) moves together, so P6 opens the file showing the %
        # that was entered whichever one the activity uses.
        pct = float(activity.percent_complete or 0)
        activity.phys_complete_pct = pct
        if target:
            activity.remaining_duration_hours = round(target * (1 - pct / 100), 4)
            activity.remaining_duration_days = round(activity.remaining_duration_hours / hpd)
    elif remaining_entered:
        activity.remaining_duration_hours = float(activity.remaining_duration_days) * hpd

    if pct_entered or status_changed:
        apply_units_from_progress(activity, [*labor, *(nonlabor or [])])

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
    """Finished work has no float: blank, as P6 writes it (not 0)."""
    if activity.status == ActivityStatus.complete:
        activity.total_float_hours = None
        activity.free_float_hours = None
        activity.is_critical = False
