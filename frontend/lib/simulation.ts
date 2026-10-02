// Schedule Simulation — types for /projects/{id}/simulations/* (backend/app/
// api/routes/simulations.py) and the page's scenario helpers. The simulation
// itself runs server-side (services/schedule_simulation.py): it reschedules a
// copy of the current programme with the changes and compares it with the
// same programme, unchanged, at the same simulation data date.
//
// A change is an activity edited the way Project Activities edits it (status,
// actual dates, % complete, remaining duration) plus P6's Expected Finish or
// "finishes N working days later" — kind "progress". Scenarios saved before
// that carry one single-field change each; toDraft() reads those too.

import { fmtP6Date } from "@/components/reporting/format";
import { toDays } from "@/lib/duration";
import { displayFinish, displayStart, FINISH_MILESTONE, isMilestone, START_MILESTONE } from "@/lib/schedule-dates";
import type { Activity, ActivityStatus } from "@/lib/types";

export type SimEditKind =
  | "progress"
  | "complete"
  | "actual_start"
  | "percent_complete"
  | "remaining_duration"
  | "finish_delay"
  | "finish_on";

export interface SimEdit {
  external_id: string;
  kind: SimEditKind;
  /** Single-field kinds only (older scenarios). */
  value?: string | number | null;
  actual_start?: string | null;
  status?: ActivityStatus | null;
  actual_finish?: string | null;
  percent_complete?: number | null;
  remaining_days?: number | null;
  expected_finish?: string | null;
  finish_delay_days?: number | null;
}

export interface SimContext {
  has_schedule: boolean;
  import_id: string | null;
  revision_label: string | null;
  imported_at: string | null;
  current_data_date: string | null;
}

/** An activity as edited in the scenario — the same fields Project Activities
 *  edits, plus the two ways to say "it finishes later". */
export interface Draft {
  status: ActivityStatus;
  actual_start: string | null;
  actual_finish: string | null;
  percent_complete: number;
  remaining_days: number;
  expected_finish: string | null;
  finish_delay_days: number | null;
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

// --- drafts --------------------------------------------------------------------------

export const SUMMARY_TYPES = new Set(["TT_LOE", "TT_WBS"]);

/** Remaining duration in the activity's own calendar days. */
export function remainingDays(a: Activity): number {
  const d = toDays(a.remaining_duration_hours, a);
  return Math.round((d ?? a.remaining_duration_days ?? 0) * 100) / 100;
}

export function originalDays(a: Activity): number | null {
  const d = toDays(a.target_duration_hours, a);
  return d == null ? null : Math.round(d * 100) / 100;
}

/** The activity as the live schedule has it. */
export function liveDraft(a: Activity): Draft {
  return {
    status: a.status,
    actual_start: a.actual_start ?? null,
    actual_finish: a.actual_finish ?? null,
    percent_complete: a.percent_complete ?? 0,
    remaining_days: remainingDays(a),
    expected_finish: null,
    finish_delay_days: null,
  };
}

export function sameDraft(x: Draft, y: Draft): boolean {
  return (
    x.status === y.status &&
    (x.actual_start ?? null) === (y.actual_start ?? null) &&
    (x.actual_finish ?? null) === (y.actual_finish ?? null) &&
    x.percent_complete === y.percent_complete &&
    Math.abs(x.remaining_days - y.remaining_days) < 0.005 &&
    (x.expected_finish ?? null) === (y.expected_finish ?? null) &&
    (x.finish_delay_days || 0) === (y.finish_delay_days || 0)
  );
}

/** A scenario change -> the draft it stands for (older single-field changes
 *  included). */
export function toDraft(e: SimEdit, a: Activity, simDate: string): Draft {
  const live = liveDraft(a);
  const original = originalDays(a) ?? live.remaining_days;
  switch (e.kind) {
    case "progress":
      return {
        status: e.status ?? live.status,
        actual_start: e.actual_start ?? null,
        actual_finish: e.actual_finish ?? null,
        percent_complete: e.percent_complete ?? live.percent_complete,
        remaining_days: e.remaining_days ?? live.remaining_days,
        expected_finish: e.expected_finish ?? null,
        finish_delay_days: e.finish_delay_days ?? null,
      };
    case "complete": {
      const on = typeof e.value === "string" && e.value ? e.value : simDate;
      return { ...live, status: "complete", actual_start: e.actual_start ?? live.actual_start ?? on, actual_finish: on, percent_complete: 100, remaining_days: 0 };
    }
    case "actual_start":
      return { ...live, status: "in_progress", actual_start: typeof e.value === "string" ? e.value : simDate };
    case "percent_complete": {
      const pct = Number(e.value ?? 0);
      return {
        ...live,
        status: "in_progress",
        actual_start: live.actual_start ?? simDate,
        percent_complete: pct,
        remaining_days: Math.round(original * (1 - pct / 100) * 100) / 100,
      };
    }
    case "remaining_duration":
      return { ...live, remaining_days: Number(e.value ?? 0) };
    case "finish_delay":
      return { ...live, finish_delay_days: Number(e.value ?? 0) };
    case "finish_on":
      return { ...live, expected_finish: typeof e.value === "string" ? e.value : null };
  }
}

export function toEdit(a: Activity, d: Draft): SimEdit {
  return {
    external_id: a.external_id,
    kind: "progress",
    status: d.status,
    actual_start: d.status === "not_started" ? null : d.actual_start,
    actual_finish: d.status === "complete" ? d.actual_finish : null,
    percent_complete: d.percent_complete,
    remaining_days: d.remaining_days,
    expected_finish: d.status === "complete" ? null : d.expected_finish,
    finish_delay_days: d.status === "complete" ? null : d.finish_delay_days || null,
  };
}

/** The draft after picking a status — the dates the status implies, as the
 *  Activity modal does, but defaulting to the simulation data date. */
export function withStatus(a: Activity, d: Draft, next: ActivityStatus, simDate: string): Draft {
  const plannedStart = displayStart(a);
  const startDefault = d.actual_start ?? (plannedStart && plannedStart.slice(0, 10) <= simDate ? plannedStart.slice(0, 10) : simDate);
  if (isMilestone(a)) {
    if (next === "complete") {
      const on = d.actual_finish ?? d.actual_start ?? simDate;
      return { ...d, status: next, actual_start: on, actual_finish: on, percent_complete: 100, remaining_days: 0, expected_finish: null, finish_delay_days: null };
    }
    return { ...d, status: "not_started", actual_start: null, actual_finish: null, percent_complete: 0 };
  }
  if (next === "not_started") {
    const original = originalDays(a);
    return {
      ...d,
      status: next,
      actual_start: null,
      actual_finish: null,
      percent_complete: 0,
      remaining_days: a.status === "not_started" ? remainingDays(a) : original ?? d.remaining_days,
    };
  }
  if (next === "in_progress") {
    return {
      ...d,
      status: next,
      actual_start: startDefault,
      actual_finish: null,
      percent_complete: d.percent_complete >= 100 ? 99 : d.percent_complete,
      remaining_days: d.status === "complete" ? originalDays(a) ?? d.remaining_days : d.remaining_days,
    };
  }
  return {
    ...d,
    status: next,
    actual_start: startDefault,
    actual_finish: d.actual_finish ?? simDate,
    percent_complete: 100,
    remaining_days: 0,
    expected_finish: null,
    finish_delay_days: null,
  };
}

/** % entered -> remaining follows it (remaining = original x (1 - %)), the
 *  rule Project Activities applies. */
export function withPercent(a: Activity, d: Draft, pct: number): Draft {
  const original = originalDays(a);
  const p = Math.max(0, Math.min(100, pct));
  return {
    ...d,
    percent_complete: p,
    remaining_days: original == null ? d.remaining_days : Math.round(original * (1 - p / 100) * 100) / 100,
  };
}

/** Mirrors the server's checks so Run is blocked before a round trip. */
export function validateDraft(a: Activity, d: Draft, simDate: string): string | null {
  const milestone = isMilestone(a);
  if (SUMMARY_TYPES.has(a.task_type ?? "")) return "Summary and level-of-effort activities follow the others; they can't be changed here.";
  if (milestone && d.status === "in_progress") return "A milestone is never in progress.";
  for (const v of [d.actual_start, d.actual_finish]) {
    if (v && v > simDate) return `Actual dates can't be after the simulation data date (${fmtP6Date(simDate)}).`;
  }
  if (!milestone && d.status === "complete" && !d.actual_finish) return "A completed activity needs an Actual Finish.";
  if (!milestone && d.actual_start && d.actual_finish && d.actual_finish < d.actual_start) return "Actual Finish is before Actual Start.";
  if (d.status === "in_progress" && d.percent_complete >= 100) return "100% is complete: set the status to Completed.";
  if (Number.isNaN(d.remaining_days) || d.remaining_days < 0) return "Remaining duration can't be negative.";
  if (d.status !== "complete" && d.expected_finish && d.expected_finish <= simDate)
    return "Pick an expected finish after the simulation data date.";
  if (milestone && (d.finish_delay_days ?? 0) < 0) return "Move a milestone later only; its logic sets how early it can be.";
  return null;
}

/** One line for the changes list: what the scenario does to the activity. */
export function draftSummary(a: Activity, d: Draft): string {
  const milestone = isMilestone(a);
  const parts: string[] = [];
  if (d.status !== a.status) {
    parts.push(
      d.status === "complete"
        ? `${milestone ? "Achieved" : "Completed"} ${fmtP6Date(d.actual_finish ?? d.actual_start)}`
        : d.status === "in_progress"
          ? `Started ${fmtP6Date(d.actual_start)}`
          : "Back to not started",
    );
  } else if (d.status === "complete" && d.actual_finish !== (a.actual_finish ?? null)) {
    parts.push(`Finished ${fmtP6Date(d.actual_finish)}`);
  } else if (d.actual_start !== (a.actual_start ?? null) && d.actual_start) {
    parts.push(`Started ${fmtP6Date(d.actual_start)}`);
  }
  if (d.status === "in_progress" && d.percent_complete !== a.percent_complete) parts.push(`${d.percent_complete}%`);
  if (d.status !== "complete" && Math.abs(d.remaining_days - remainingDays(a)) >= 0.005)
    parts.push(`${Math.round(d.remaining_days * 10) / 10}d remaining`);
  if (d.status !== "complete" && d.expected_finish) parts.push(`${milestone ? "Moved to" : "Expected finish"} ${fmtP6Date(d.expected_finish)}`);
  if (d.status !== "complete" && d.finish_delay_days) parts.push(`${d.finish_delay_days > 0 ? "+" : "−"}${Math.abs(d.finish_delay_days)}d later`);
  return parts.join(" · ") || "No change";
}

/** The dates the grid shows for a changed activity before the run: actuals
 *  from the draft, the live schedule's dates otherwise. */
export function draftDates(a: Activity, d: Draft): { start: string | null; finish: string | null } {
  const live = { start: displayStart(a), finish: displayFinish(a) };
  const start = a.task_type === FINISH_MILESTONE ? null : d.status === "not_started" ? (a.status === "not_started" ? live.start : null) : d.actual_start;
  const finish =
    a.task_type === START_MILESTONE
      ? null
      : d.status === "complete"
        ? d.actual_finish
        : d.expected_finish ?? (a.status === "complete" ? null : live.finish);
  return { start, finish };
}

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

/** Stringified inputs of a run — results are stale once this changes. */
export function runKey(dataDate: string, edits: SimEdit[]): string {
  return JSON.stringify([dataDate, edits]);
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
