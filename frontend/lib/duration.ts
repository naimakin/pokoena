// Hours → days the way P6 shows them. P6 stores every duration and float in
// hours and divides by the activity's OWN calendar's day length:
//
//   Total Float (d)       = TASK.total_float_hr_cnt / CALENDAR.day_hr_cnt
//   Original Duration (d) = TASK.target_drtn_hr_cnt / CALENDAR.day_hr_cnt
//
// The backend serves that divisor per activity as `hours_per_day` (see
// backend/app/engine/durations.py) — never divide by a flat 8.

export const DEFAULT_HOURS_PER_DAY = 8;

type HasCalendar = { hours_per_day?: number | null } | null | undefined;

/** The activity's calendar day length, or 8 when it has no calendar. */
export function hoursPerDay(a: HasCalendar): number {
  const h = a?.hours_per_day;
  return h != null && h > 0 ? h : DEFAULT_HOURS_PER_DAY;
}

/** One of the activity's own hour fields, in that activity's days. */
export function toDays(hours: number | null | undefined, a: HasCalendar): number | null {
  return hours == null ? null : hours / hoursPerDay(a);
}
