"""CalendarEngine.work_hours_between counts whole days through a running
total instead of walking every day in between. It has to agree, to the
hour-fraction, with the walk it replaced — including exception days, split
shifts and a shift that ends at midnight."""

import random
from datetime import datetime, time, timedelta

from app.engine.cpm.calendar_engine import CalendarEngine
from app.parser.xer_models import Calendar, CalendarDay, CalendarException, DayShift


def _walk(eng: CalendarEngine, start: datetime, end: datetime) -> float:
    """The original day-by-day implementation."""
    if end < start:
        return -_walk(eng, end, start)
    total = 0.0
    current = start
    while current.date() <= end.date():
        for shift in eng._get_day_def(current).shifts:
            s_start = current.replace(hour=shift.start.hour, minute=shift.start.minute, second=0, microsecond=0)
            s_end = current.replace(hour=shift.end.hour, minute=shift.end.minute, second=0, microsecond=0)
            lo, hi = max(current, s_start), min(end, s_end)
            if hi > lo:
                total += (hi - lo).total_seconds() / 3600
        current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return round(total, 6)


def _calendar() -> Calendar:
    day = [DayShift(time(8, 0), time(12, 0)), DayShift(time(13, 0), time(17, 30))]
    week = [CalendarDay(0, [])] + [CalendarDay(d, day) for d in range(1, 6)] + [CalendarDay(6, [DayShift(time(16, 0), time(0, 0))])]
    exceptions = [
        CalendarException(datetime(2026, 1, 1), []),
        CalendarException(datetime(2026, 4, 23), []),
        CalendarException(datetime(2026, 2, 7), [DayShift(time(9, 0), time(13, 0))]),
    ]
    return Calendar(clndr_id="C", clndr_name="Split", default_work_week=week, exceptions=exceptions, hours_per_day=8.5)


def test_fast_path_matches_the_day_walk():
    eng = CalendarEngine(_calendar())
    ref = CalendarEngine(_calendar())
    rnd = random.Random(7)
    base = datetime(2026, 1, 5, 8, 0)
    for _ in range(2000):
        a = base + timedelta(minutes=rnd.randint(-300 * 1440, 300 * 1440))
        b = base + timedelta(minutes=rnd.randint(-300 * 1440, 300 * 1440))
        assert abs(eng.work_hours_between(a, b) - _walk(ref, a, b)) < 1e-6, (a, b)
