"""Calendar-aware date arithmetic used by the CPM scheduler. All durations and
lags are in hours. Ported from the reference project's `calendar_engine.py`,
unchanged except the import path (`app.parser.xer_models` instead of
`app.models.xer_models`)."""

from __future__ import annotations

from datetime import datetime, timedelta
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
        self._exc: dict[str, CalendarException] = {
            ex.exc_date.strftime("%Y-%m-%d"): ex for ex in calendar.exceptions
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _day_key(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

    def _get_day_def(self, dt: datetime) -> CalendarDay:
        """Return the effective CalendarDay for a given date (exception overrides week)."""
        key = self._day_key(dt)
        if key in self._exc:
            exc = self._exc[key]
            return CalendarDay(day_of_week=dt.weekday(), shifts=exc.shifts)
        # P6 weekday: 0=Sun...6=Sat; Python weekday: 0=Mon...6=Sun.
        p6_dow = (dt.weekday() + 1) % 7
        return self._week.get(p6_dow, CalendarDay(day_of_week=p6_dow, shifts=[]))

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

        total = 0.0
        current = start
        end_date = end.date()

        while current.date() <= end_date:
            day_def = self._get_day_def(current)
            for shift in day_def.shifts:
                s_start = current.replace(hour=shift.start.hour, minute=shift.start.minute, second=0, microsecond=0)
                s_end = current.replace(hour=shift.end.hour, minute=shift.end.minute, second=0, microsecond=0)
                overlap_start = max(current, s_start)
                overlap_end = min(end, s_end)
                if overlap_end > overlap_start:
                    total += (overlap_end - overlap_start).total_seconds() / 3600
            current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        return round(total, 6)

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
