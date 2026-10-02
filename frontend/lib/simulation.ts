// Schedule Simulation — types for /projects/{id}/simulations/* (backend/app/
// api/routes/simulations.py) and the page's scenario helpers. The simulation
// itself runs server-side (services/schedule_simulation.py): it reschedules a
// copy of the current programme with the changes and compares it with the
// same programme, unchanged, at the same simulation data date.

import { fmtP6Date } from "@/components/reporting/format";

export type SimEditKind =
  | "complete"
  | "actual_start"
  | "percent_complete"
  | "remaining_duration"
  | "finish_delay"
  | "finish_on";

export interface SimEdit {
  external_id: string;
  kind: SimEditKind;
  /** ISO date for complete / actual_start / finish_on; a number otherwise
   *  (percent 0-100, or days on the activity's own calendar). */
  value: string | number | null;
  actual_start?: string | null;
}

export interface SimContextActivity {
  id: string;
  external_id: string;
  name: string;
  wbs_name: string | null;
  task_type: string | null;
  is_milestone: boolean;
  status: "not_started" | "in_progress" | "complete";
  start: string | null;
  finish: string | null;
  total_float_days: number | null;
  remaining_days: number;
  original_days: number | null;
  percent_complete: number;
  hours_per_day: number;
}

export interface SimContext {
  has_schedule: boolean;
  import_id: string | null;
  revision_label: string | null;
  imported_at: string | null;
  current_data_date: string | null;
  activities: SimContextActivity[];
}

export type SimDriver =
  | { kind: "edit"; summary: string }
  | { kind: "predecessor"; external_id: string; name: string; link_type: string; lag_days: number }
  | { kind: "constraint"; label: string; date: string | null }
  | { kind: "data_date" }
  | { kind: "actual" };

export interface SimRow {
  id: string;
  external_id: string;
  name: string;
  wbs_name: string | null;
  task_type: string | null;
  hours_per_day: number;
  status_before: string;
  status_after: string;
  start_before: string | null;
  start_after: string | null;
  finish_before: string | null;
  finish_after: string | null;
  start_delta_days: number | null;
  finish_delta_days: number;
  direction: "later" | "earlier" | "same";
  total_float_before_days: number | null;
  total_float_after_days: number | null;
  critical_before: boolean;
  critical_after: boolean;
  longest_path_after: boolean;
  is_edited: boolean;
  driver: SimDriver;
  /** The step before this one on the driving chain back to a change. */
  cause: { external_id: string; link_type: string; lag_days: number } | null;
  is_project_finish?: boolean;
}

export interface SimWarning {
  code: string;
  external_id: string | null;
  message: string;
}

export interface SimResult {
  run_at: string;
  import_id: string;
  revision_label: string | null;
  current_data_date: string;
  simulation_data_date: string;
  total_activities: number;
  excluded_summary: number;
  project_finish: {
    external_id: string | null;
    name: string | null;
    current: string | null;
    unchanged: string | null;
    simulated: string | null;
    delta_days: number;
    data_date_delta_days: number;
    total_delta_days: number;
  };
  counts: {
    moved: number;
    later: number;
    earlier: number;
    milestones_moved: number;
    milestones_total: number;
    critical_before: number;
    critical_after: number;
    joined_critical: number;
    left_critical: number;
    data_date_moved: number;
  };
  moved: SimRow[];
  truncated: boolean;
  milestones: SimRow[];
  warnings: SimWarning[];
}

export interface SimScenario {
  id: string;
  name: string;
  simulation_data_date: string | null;
  edits: SimEdit[];
  schedule_import_id: string | null;
  revision_label: string | null;
  stale: boolean;
  last_finish_delta_days: number | null;
  last_run_at: string | null;
  created_by_name: string | null;
  is_owner: boolean;
  can_change: boolean;
  updated_at: string | null;
}

/** A 422 from /run: {code, message, errors?: [{external_id, message}]}. */
export interface SimErrorDetail {
  code: string;
  message: string;
  errors?: { external_id: string; message: string }[];
}

export function isSimErrorDetail(d: unknown): d is SimErrorDetail {
  return Boolean(d && typeof d === "object" && "code" in d && "message" in d);
}

// --- change kinds ------------------------------------------------------------------

export const KIND_LABEL: Record<SimEditKind, string> = {
  complete: "Mark complete",
  actual_start: "Set actual start",
  percent_complete: "Set % complete",
  remaining_duration: "Set remaining duration",
  finish_delay: "Finish later by",
  finish_on: "Finish on date",
};

const MILESTONE_LABEL: Partial<Record<SimEditKind, string>> = {
  complete: "Achieved on",
  finish_delay: "Move by",
  finish_on: "Move to date",
};

export function kindLabel(kind: SimEditKind, milestone: boolean): string {
  return (milestone && MILESTONE_LABEL[kind]) || KIND_LABEL[kind];
}

/** The change types an activity can take: a milestone has one date; started
 *  work can't be "started" again. */
export function kindOptions(a: SimContextActivity): SimEditKind[] {
  if (a.is_milestone) return ["complete", "finish_delay", "finish_on"];
  const all: SimEditKind[] = ["complete", "finish_delay", "finish_on", "percent_complete", "remaining_duration"];
  return a.status === "not_started" ? [...all, "actual_start"] : all;
}

export const DATE_KINDS = new Set<SimEditKind>(["complete", "actual_start", "finish_on"]);

// --- dates (ISO yyyy-mm-dd, compared as strings) ------------------------------------

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function addMonths(iso: string, months: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + months);
  return d.toISOString().slice(0, 10);
}

export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

/** A sensible first change for a newly added activity. */
export function defaultEdit(a: SimContextActivity, simDate: string): SimEdit {
  if (a.is_milestone) {
    const base = a.finish ?? a.start ?? simDate;
    return { external_id: a.external_id, kind: "finish_on", value: addDays(base > simDate ? base : simDate, 7) };
  }
  if (a.status === "in_progress") return { external_id: a.external_id, kind: "complete", value: simDate };
  return { external_id: a.external_id, kind: "finish_delay", value: 15 };
}

/** The value an edit takes when its kind changes. */
export function valueForKind(kind: SimEditKind, a: SimContextActivity, simDate: string): string | number {
  switch (kind) {
    case "complete":
    case "actual_start":
      return simDate;
    case "finish_on": {
      const base = a.finish ?? simDate;
      return addDays(base > simDate ? base : simDate, 7);
    }
    case "percent_complete":
      return Math.min(99, Math.max(0, Math.round(a.percent_complete || 50)));
    case "remaining_duration":
      return Math.round(a.remaining_days * 10) / 10;
    case "finish_delay":
      return 15;
  }
}

/** Mirrors the server's checks so Run is blocked before a round trip. */
export function validateEdit(e: SimEdit, a: SimContextActivity | undefined, simDate: string): string | null {
  if (!a) return "This activity isn't in the current programme.";
  if (a.status === "complete") return "This activity is already complete in the live schedule.";
  const v = e.value;
  if (DATE_KINDS.has(e.kind)) {
    if (e.kind !== "complete" && (typeof v !== "string" || !v)) return "Pick a date.";
    if (e.kind === "finish_on") {
      if (typeof v === "string" && v <= simDate)
        return "Pick a date after the simulation data date; use Mark complete for finished work.";
      return null;
    }
    if (typeof v === "string" && v > simDate)
      return `Actual dates can't be after the simulation data date (${fmtP6Date(simDate)}).`;
    if (e.kind === "complete" && e.actual_start && typeof v === "string" && e.actual_start > v)
      return "The finish can't be before the start.";
    return null;
  }
  if (typeof v !== "number" || Number.isNaN(v)) return "Enter a number.";
  if (e.kind === "percent_complete" && (v < 0 || v > 100)) return "% complete must be between 0 and 100.";
  if (e.kind === "remaining_duration" && v < 0) return "Remaining duration can't be negative.";
  if (e.kind === "finish_delay" && a.is_milestone && v <= 0)
    return "Move a milestone by a positive number of days; its logic sets how early it can be.";
  return null;
}

/** Stringified inputs of a run — results are stale once this changes. */
export function runKey(dataDate: string, edits: SimEdit[]): string {
  return JSON.stringify([dataDate, edits.map((e) => [e.external_id, e.kind, e.value, e.actual_start ?? null])]);
}

// --- results -------------------------------------------------------------------------

/** "FS", "SS +2d", "FS −1d". */
export function linkText(type: string, lagDays: number): string {
  if (!lagDays) return type;
  const r = Math.round(lagDays * 10) / 10;
  return `${type} ${r > 0 ? "+" : "−"}${Math.abs(r)}d`;
}

/** Signed working days: "+9d", "−4d", "0d". */
export function signedDays(days: number | null | undefined): string {
  if (days == null) return "—";
  const r = Math.round(days * 10) / 10;
  if (r === 0) return "0d";
  return `${r > 0 ? "+" : "−"}${Math.abs(r)}d`;
}

export function deltaClass(days: number | null | undefined): string {
  const r = Math.round((days ?? 0) * 10) / 10;
  return `sim-delta ${r > 0 ? "is-later" : r < 0 ? "is-earlier" : "is-zero"}`;
}

/** The driving chain from a change to `row` (change first), walked through
 *  each row's `cause`. Guards against a loop in malformed data. */
export function walkChain(row: SimRow, byId: Map<string, SimRow>): SimRow[] {
  const chain: SimRow[] = [row];
  const seen = new Set([row.external_id]);
  let cur: SimRow | undefined = row;
  while (cur?.cause) {
    const next = byId.get(cur.cause.external_id);
    if (!next || seen.has(next.external_id)) break;
    chain.push(next);
    seen.add(next.external_id);
    cur = next;
  }
  return chain.reverse();
}

export function driverText(d: SimDriver): string {
  switch (d.kind) {
    case "edit":
      return `Your change: ${d.summary}`;
    case "predecessor":
      return `${d.external_id} ${linkText(d.link_type, d.lag_days)}`;
    case "constraint":
      return d.date ? `${d.label} ${fmtP6Date(d.date)}` : d.label;
    case "data_date":
      return "Data date";
    case "actual":
      return "Actual dates";
  }
}

export function movedCsv(rows: SimRow[]): string {
  const head = [
    "Activity ID", "Name", "WBS", "Start before", "Start after", "Finish before", "Finish after",
    "Finish change (d)", "Total float before (d)", "Total float after (d)", "Critical before", "Critical after",
    "Driven by", "Your change",
  ];
  const lines = rows.map((r) => [
    r.external_id,
    r.name,
    r.wbs_name ?? "",
    r.start_before ? fmtP6Date(r.start_before) : "",
    r.start_after ? fmtP6Date(r.start_after) : "",
    r.finish_before ? fmtP6Date(r.finish_before) : "",
    r.finish_after ? fmtP6Date(r.finish_after) : "",
    String(r.finish_delta_days),
    r.total_float_before_days ?? "",
    r.total_float_after_days ?? "",
    r.critical_before ? "Yes" : "No",
    r.critical_after ? "Yes" : "No",
    driverText(r.driver),
    r.is_edited ? "Yes" : "No",
  ]);
  return [head, ...lines].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\r\n");
}

export function downloadText(text: string, filename: string, type = "text/csv;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
