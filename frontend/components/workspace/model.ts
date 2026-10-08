// Shared helpers for Programme > Activity Workspace (the merged Activity
// Ledger + Chart page): date formatting, the Gantt's date picks, and the
// per-browser view preferences.

import { hoursPerDay } from "@/lib/duration";
import type { Activity } from "@/lib/types";

export const MS_DAY = 86_400_000;
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Grid row height. The grid and the Gantt MUST share it (and the header
 *  height), or the mirrored vertical scroll drifts row by row. */
export const ROW_H = 28;
/** Header height with the Gantt shown = timescale height: two date tiers plus
 *  the lane for the project start / data date / project end flags. */
export const HEAD_H_GANTT = 54;
/** Header height when the grid has the card to itself. */
export const HEAD_H_GRID = 36;

const GANTT_MILESTONES = new Set(["TT_Mile", "TT_FinMile", "TT_StartMile"]);

// P6 convention (DD-MMM-YYYY) — see CLAUDE.md.
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

/** Short form for the Program picker, as on Programs / Planning > WBS. */
export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(-2)}`;
}

export function isGanttMilestone(a: Activity): boolean {
  return Boolean(a.task_type && GANTT_MILESTONES.has(a.task_type));
}

// A milestone is a single point in time, and P6 shows it against the one date
// it actually has: a Start Milestone has a start and no finish, a Finish
// Milestone the other way round. Used for the baseline columns, whose source
// (the variance report) stores both dates on every activity.
export function milestoneDates(
  a: Activity,
  start: string | null,
  finish: string | null,
): { start: string | null; finish: string | null } {
  if (a.task_type === "TT_Mile" || a.task_type === "TT_StartMile") return { start, finish: null };
  if (a.task_type === "TT_FinMile") return { start: null, finish };
  return { start, finish };
}

/** Where the Gantt bar starts / ends (and the start-date sort order). */
export function earliestDate(a: Activity): string | null {
  return a.early_start ?? a.actual_start ?? a.planned_start ?? null;
}

export function latestDate(a: Activity): string | null {
  return a.early_finish ?? a.actual_finish ?? a.planned_finish ?? null;
}

/** Original duration in the activity's own calendar days. */
export function durationDays(a: Activity): number | null {
  if (a.target_duration_hours != null) return Math.round(a.target_duration_hours / hoursPerDay(a));
  const s = earliestDate(a);
  const f = latestDate(a);
  if (!s || !f) return null;
  return Math.max(Math.round((new Date(f).getTime() - new Date(s).getTime()) / MS_DAY), 0);
}

export function spanDays(start: string | null, finish: string | null): number | null {
  if (!start || !finish) return null;
  return Math.max(Math.round((new Date(finish).getTime() - new Date(start).getTime()) / MS_DAY), 0);
}

export interface BaselineDates {
  start: string | null;
  finish: string | null;
  finishVar: number | null;
}

// --- per-browser preferences ------------------------------------------------
// Conveniences only: storage can be unavailable (private mode, blocked site
// data), in which case the choice lasts for this page view.

export const GANTT_PREF_KEY = "poko:workspace:gantt";
export const COLUMNS_PREF_KEY = "poko:workspace:columns";

export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore — see above
  }
}
