"""Hours → days, the way P6 shows them.

P6 stores every duration and float in hours (TASK.target_drtn_hr_cnt,
TASK.remain_drtn_hr_cnt, TASK.total_float_hr_cnt, ...) and shows them in days
by dividing by the hours-per-day of the activity's *own* calendar:

    Total Float (d)       = TASK.total_float_hr_cnt / CALENDAR.day_hr_cnt
    Original Duration (d) = TASK.target_drtn_hr_cnt / CALENDAR.day_hr_cnt

So the same 40h of float is 5d on an 8h calendar and 4d on a 10h one — a flat
/8 (or one project-wide divisor) gets every activity on a non-8h calendar wrong.
`Calendar.hours_per_day` holds day_hr_cnt (see parser/xer_parser.py), and
`Activity.hours_per_day` reads it through the activity's clndr_id.
"""

from __future__ import annotations

from typing import Optional

# Only for activities with no calendar at all (created in Poko, or a calendar
# row that can't be found) — P6's own default day.
DEFAULT_HOURS_PER_DAY = 8.0


def valid_hours_per_day(hours_per_day: Optional[float]) -> float:
    return hours_per_day if hours_per_day and hours_per_day > 0 else DEFAULT_HOURS_PER_DAY


def activity_hours_per_day(activity: object, fallback: Optional[float] = None) -> float:
    """The activity's calendar day length; `fallback` (typically the project
    calendar's) only when it has no calendar of its own. Duck-typed (`getattr`)
    so the same call works on ORM rows and on the plain objects the engines'
    tests build."""
    return valid_hours_per_day(getattr(activity, "hours_per_day", None) or fallback)


def hours_to_days(hours: Optional[float], hours_per_day: Optional[float]) -> Optional[float]:
    if hours is None:
        return None
    return hours / valid_hours_per_day(hours_per_day)


def activity_days(
    activity: object, hours: Optional[float], fallback: Optional[float] = None
) -> Optional[float]:
    """`hours` (one of the activity's own hour fields) in that activity's days."""
    return hours_to_days(hours, activity_hours_per_day(activity, fallback))
