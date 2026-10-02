"""Calendar-aware date arithmetic used by the CPM scheduler. All durations and
lags are in hours. Ported from the reference project's `calendar_engine.py`,
unchanged except the import path (`app.parser.xer_models` instead of
`app.models.xer_models`)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from app.parser.xer_models import Calendar, CalendarDay, CalendarException


class NoWorkingDayError(ValueError):
    """A calendar has no working day within the lookahead window used to
    resolve a date onto it — most often a calendar whose `clndr_data` parsed
    to zero working days (a genuinely blank/placeholder calendar in the
    source file, or a real P6 calendar format our parser didn't read
    correctly — either way, CPM can't run against it as-is)."""


class CalendarEngine:
    """Wraps a Calendar and provides work-hour arithmetic. All public methods
    accept and return datetime objects."""

    def __init__(self, calendar: Calendar):
        self._cal = calendar
        self._week: dict[int, CalendarDay] = {d.day_of_week: d for d in calendar.default_work_week}
        self._exc: dict[date, CalendarException] = {ex.exc_date.date(): ex for ex in calendar.exceptions}
        # Per-date memo of the effective day, and a running total of work hours
        # before each day (keyed by date ordinal, relative to whichever day was
        # asked first). Together they make work_hours_between O(1) across days
        # instead of a walk over every day in between — the walk was most of
        # a schedule() run on a multi-year programme.
        self._day_memo: dict[date, CalendarDay] = {}
        self._cum: dict[int, float] = {}
        self._cum_lo = 0
        self._cum_hi = -1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_day_def(self, dt: datetime | date) -> CalendarDay:
        """Return the effective CalendarDay for a given date (exception overrides week)."""
        day = dt.date() if isinstance(dt, datetime) else dt
        found = self._day_memo.get(day)
        if found is not None:
            return found
        exc = self._exc.get(day)
        if exc is not None:
            found = CalendarDay(day_of_week=day.weekday(), shifts=exc.shifts)
        else:
            # P6 weekday: 0=Sun...6=Sat; Python weekday: 0=Mon...6=Sun.
            p6_dow = (day.weekday() + 1) % 7
            found = self._week.get(p6_dow, CalendarDay(day_of_week=p6_dow, shifts=[]))
        self._day_memo[day] = found
        return found

    def _hours_before_day(self, day: date) -> float:
        """Work hours in every day before `day`, counted from a fixed anchor —
        only differences between two of these mean anything."""
        o = day.toordinal()
        if self._cum_hi < self._cum_lo:  # first call: anchor here
            self._cum[o] = 0.0
            self._cum_lo = self._cum_hi = o
            return 0.0
        while o > self._cum_hi:
            self._cum[self._cum_hi + 1] = self._cum[self._cum_hi] + self._whole_day_hours(date.fromordinal(self._cum_hi))
            self._cum_hi += 1
        while o < self._cum_lo:
            self._cum[self._cum_lo - 1] = self._cum[self._cum_lo] - self._whole_day_hours(
                date.fromordinal(self._cum_lo - 1)
            )
            self._cum_lo -= 1
        return self._cum[o]

    def _whole_day_hours(self, day: date) -> float:
        """A whole day's work hours, counted the way _hours_in_day_between
        counts them (a shift ending at 00:00 adds nothing, not a negative)."""
        midnight = datetime.combine(day, datetime.min.time())
        return self._hours_in_day_between(midnight, midnight.replace(hour=23, minute=59, second=59, microsecond=999999))

    def _hours_in_day_between(self, start: datetime, end: datetime) -> float:
        """Work hours between two moments on the same day."""
        total = 0.0
        for shift in self._get_day_def(start).shifts:
            s_start = start.replace(hour=shift.start.hour, minute=shift.start.minute, second=0, microsecond=0)
            s_end = start.replace(hour=shift.end.hour, minute=shift.end.minute, second=0, microsecond=0)
            overlap_start = max(start, s_start)
            overlap_end = min(end, s_end)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds() / 3600
        return total

    def _is_working_day(self, dt: datetime) -> bool:
        return self._get_day_def(dt).is_working

    def _work_hours_in_day(self, dt: datetime) -> float:
        return self._get_day_def(dt).total_hours

    def _hours_remaining_from(self, dt: datetime) -> float:
        """Work hours remaining in dt's day starting from dt's time."""
        day_def = self._get_day_def(dt)
        total = 0.0
        for shift in day_def.shifts:
            s_start_h = shift.start.hour + shift.start.minute / 60
            s_end_h = shift.end.hour + shift.end.minute / 60
            cur_h = dt.hour + dt.minute / 60 + dt.second / 3600

            if cur_h >= s_end_h:
                continue
            elif cur_h <= s_start_h:
                total += s_end_h - s_start_h
            else:
                total += s_end_h - cur_h
        return total

    def _hours_elapsed_up_to(self, dt: datetime) -> float:
        """Work hours elapsed in dt's day up to dt's time."""
        day_def = self._get_day_def(dt)
        total = 0.0
        for shift in day_def.shifts:
            s_start_h = shift.start.hour + shift.start.minute / 60
            s_end_h = shift.end.hour + shift.end.minute / 60
            cur_h = dt.hour + dt.minute / 60 + dt.second / 3600

            if cur_h <= s_start_h:
                break
            elif cur_h >= s_end_h:
                total += s_end_h - s_start_h
            else:
                total += cur_h - s_start_h
        return total

    def _day_work_start(self, dt: datetime) -> Optional[datetime]:
        day_def = self._get_day_def(dt)
        if not day_def.shifts:
            return None
        first = day_def.shifts[0].start
        return dt.replace(hour=first.hour, minute=first.minute, second=0, microsecond=0)

    def _day_work_end(self, dt: datetime) -> Optional[datetime]:
        day_def = self._get_day_def(dt)
        if not day_def.shifts:
            return None
        last = day_def.shifts[-1].end
        return dt.replace(hour=last.hour, minute=last.minute, second=0, microsecond=0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snap_to_work_start(self, dt: datetime) -> datetime:
        """If dt falls on a non-working day or outside work hours, advance to
        the next work start. Duration is NOT affected."""
        candidate = dt
        for _ in range(365):
            ws = self._day_work_start(candidate)
            if ws is not None:
                if candidate.hour * 60 + candidate.minute < ws.hour * 60 + ws.minute:
                    return ws
                day_def = self._get_day_def(candidate)
                for shift in day_def.shifts:
                    s_start_h = shift.start.hour + shift.start.minute / 60
                    s_end_h = shift.end.hour + shift.end.minute / 60
                    cur_h = candidate.hour + candidate.minute / 60
                    if s_start_h <= cur_h <= s_end_h:
                        return candidate
            candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        raise NoWorkingDayError(
            f"Calendar {self._cal.clndr_id!r} ({self._cal.clndr_name!r}) has no working day "
            f"within 365 days of {dt} — check its working week in P6."
        )

    def add_work_hours(self, dt: datetime, hours: float) -> datetime:
        """Add `hours` work hours to `dt`, skipping non-working days/gaps.
        Duration is never modified."""
        if hours == 0:
            return dt

        remaining = hours
        current = self.snap_to_work_start(dt)

        for _ in range(3650):
            day_remaining = self._hours_remaining_from(current)

            if day_remaining <= 0:
                next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                current = self.snap_to_work_start(next_day)
                continue

            if remaining <= day_remaining:
                return self._advance_within_day(current, remaining)
            else:
                remaining -= day_remaining
                next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                current = self.snap_to_work_start(next_day)

        raise NoWorkingDayError(
            f"Calendar {self._cal.clndr_id!r} ({self._cal.clndr_name!r}) couldn't advance {hours}h "
            f"from {dt} — check its working week in P6."
        )

    def sub_work_hours(self, dt: datetime, hours: float) -> datetime:
        """Subtract `hours` work hours from `dt` (go backwards)."""
        if hours == 0:
            return dt

        remaining = hours
        current = dt

        for _ in range(3650):
            day_elapsed = self._hours_elapsed_up_to(current)

            if day_elapsed <= 0:
                prev_day = (current - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
                we = self._day_work_end(prev_day)
                current = we if we else prev_day
                continue

            if remaining <= day_elapsed:
                return self._retreat_within_day(current, remaining)
            else:
                remaining -= day_elapsed
                prev_day = (current - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
                we = self._day_work_end(prev_day)
                current = we if we else prev_day

        raise NoWorkingDayError(
            f"Calendar {self._cal.clndr_id!r} ({self._cal.clndr_name!r}) couldn't retreat {hours}h "
            f"from {dt} — check its working week in P6."
        )

    def work_hours_between(self, start: datetime, end: datetime) -> float:
        """Count net work hours between two datetimes. Negative if end < start."""
        if end < start:
            return -self.work_hours_between(end, start)
        if start.date() == end.date():
            return round(self._hours_in_day_between(start, end), 6)

        # The rest of start's day + every whole day in between + end's day up to end.
        start_day, end_day = start.date(), end.date()
        day_start = datetime.combine(start_day, datetime.min.time())
        day_end = datetime.combine(end_day, datetime.min.time())
        rest_of_start_day = self._whole_day_hours(start_day) - self._hours_in_day_between(day_start, start)
        whole_days = self._hours_before_day(end_day) - self._hours_before_day(start_day + timedelta(days=1))
        return round(rest_of_start_day + whole_days + self._hours_in_day_between(day_end, end), 6)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _advance_within_day(self, dt: datetime, hours: float) -> datetime:
        remaining = hours
        day_def = self._get_day_def(dt)
        cur_h = dt.hour + dt.minute / 60 + dt.second / 3600

        for shift in day_def.shifts:
            s_start_h = shift.start.hour + shift.start.minute / 60
            s_end_h = shift.end.hour + shift.end.minute / 60

            if cur_h >= s_end_h:
                continue

            effective_start = max(cur_h, s_start_h)
            available = s_end_h - effective_start

            if remaining <= available:
                target_h = effective_start + remaining
                h = int(target_h)
                m = int(round((target_h - h) * 60))
                if m == 60:
                    h += 1
                    m = 0
                return dt.replace(hour=h, minute=m, second=0, microsecond=0)
            else:
                remaining -= available
                cur_h = s_end_h

        last = day_def.shifts[-1].end
        return dt.replace(hour=last.hour, minute=last.minute, second=0, microsecond=0)

    def _retreat_within_day(self, dt: datetime, hours: float) -> datetime:
        remaining = hours
        day_def = self._get_day_def(dt)
        cur_h = dt.hour + dt.minute / 60 + dt.second / 3600

        for shift in reversed(day_def.shifts):
            s_start_h = shift.start.hour + shift.start.minute / 60
            s_end_h = shift.end.hour + shift.end.minute / 60

            if cur_h <= s_start_h:
                continue

            effective_end = min(cur_h, s_end_h)
            available = effective_end - s_start_h

            if remaining <= available:
                target_h = effective_end - remaining
                h = int(target_h)
                m = int(round((target_h - h) * 60))
                if m == 60:
                    h += 1
                    m = 0
                return dt.replace(hour=h, minute=m, second=0, microsecond=0)
            else:
                remaining -= available
                cur_h = s_start_h

        first = day_def.shifts[0].start
        return dt.replace(hour=first.hour, minute=first.minute, second=0, microsecond=0)
