"""Fallback calendar: Mon-Fri, 08:00-17:00 (8 hours/day). Used when a XER file
contains no CALENDAR table. Ported from the reference project, unchanged."""

from datetime import time

from app.parser.xer_models import Calendar, CalendarDay, DayShift

_WORK_SHIFT = [DayShift(start=time(8, 0), end=time(17, 0))]
_NO_SHIFT: list = []


def make_default_calendar() -> Calendar:
    week = [
        CalendarDay(day_of_week=0, shifts=_NO_SHIFT),  # Sun
        CalendarDay(day_of_week=1, shifts=_WORK_SHIFT),  # Mon
        CalendarDay(day_of_week=2, shifts=_WORK_SHIFT),  # Tue
        CalendarDay(day_of_week=3, shifts=_WORK_SHIFT),  # Wed
        CalendarDay(day_of_week=4, shifts=_WORK_SHIFT),  # Thu
        CalendarDay(day_of_week=5, shifts=_WORK_SHIFT),  # Fri
        CalendarDay(day_of_week=6, shifts=_NO_SHIFT),  # Sat
    ]
    return Calendar(
        clndr_id="DEFAULT",
        clndr_name="Default 5-Day Calendar",
        default_work_week=week,
        exceptions=[],
        hours_per_day=8.0,
    )
