// P6's Start / Finish columns: one date per column, picked from the actual or
// the early (scheduled) date by the activity's status and type.
//
//   Not started   Start = early_start_date   Finish = early_end_date
//   In progress   Start = act_start_date     Finish = early_end_date
//   Completed     Start = act_start_date     Finish = act_end_date
//
// A milestone has only one date. TT_Mile (start milestone) shows it in Start
// with Finish blank; TT_FinMile (finish milestone) in Finish with Start blank —
// the early date while not started, the actual once completed.
//
// The early dates are P6's own TASK.early_start_date/early_end_date (see
// backend/app/services/xer_import.py). Poko-created activities have none, so
// they fall back to their planned dates.

import type { Activity } from "@/lib/types";

type Dated = Pick<
  Activity,
  "status" | "task_type" | "early_start" | "early_finish" | "actual_start" | "actual_finish" | "planned_start" | "planned_finish"
>;

export const START_MILESTONE = "TT_Mile";
export const FINISH_MILESTONE = "TT_FinMile";

export function isMilestone(a: Pick<Activity, "task_type">): boolean {
  return a.task_type === START_MILESTONE || a.task_type === FINISH_MILESTONE;
}

const earlyStart = (a: Dated) => a.early_start ?? a.planned_start ?? null;
const earlyFinish = (a: Dated) => a.early_finish ?? a.planned_finish ?? null;

export function displayStart(a: Dated): string | null {
  if (a.task_type === FINISH_MILESTONE) return null;
  if (a.status === "not_started") return earlyStart(a);
  return a.actual_start ?? null;
}

export function displayFinish(a: Dated): string | null {
  if (a.task_type === START_MILESTONE) return null;
  if (a.status === "complete") return a.actual_finish ?? null;
  return earlyFinish(a);
}
