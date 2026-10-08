// Client-side activity filter model for the Progress page. The saved-filter
// `criteria` blob the backend stores is exactly `FilterCriteria` (+ a
// `filter_version`); the backend never parses it.

import { toDays } from "@/lib/duration";
import { displayFinish, displayStart, FINISH_MILESTONE, START_MILESTONE } from "@/lib/schedule-dates";
import type { Activity, ActivityStatus, WbsNode } from "@/lib/types";

export type FieldType = "text" | "enum" | "bool" | "number" | "date";

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  ops: FilterOp[];
  // value from an activity, in the unit the operators compare against
  get: (a: Activity, ctx: FilterContext) => string | number | boolean | null;
  enumValues?: { value: string; label: string }[];
}

export type FilterOp =
  | "contains"
  | "starts_with"
  | "equals"
  | "in"
  | "is"
  | "lte"
  | "gte"
  | "between"
  | "is_empty"
  | "is_set"
  | "before"
  | "after";

export const OP_LABEL: Record<FilterOp, string> = {
  contains: "contains",
  starts_with: "starts with",
  equals: "equals",
  in: "is any of",
  is: "is",
  lte: "≤",
  gte: "≥",
  between: "between",
  is_empty: "is empty",
  is_set: "is set",
  before: "before",
  after: "after",
};

export interface FilterPredicate {
  field: string;
  op: FilterOp;
  value: string;
  value2?: string; // "between" upper bound
}

// --- quick filters (the second row of the filter card) ---------------------

export type DateAnchor = "today" | "data_date" | "fixed";
export type DatePreset = "prev_7" | "prev_14" | "prev_30" | "prev_3m" | "next_7" | "next_14" | "next_30" | "next_3m";

export const DATE_PRESETS: { key: DatePreset; label: string }[] = [
  { key: "prev_7", label: "Previous 7 days" },
  { key: "prev_14", label: "Previous 14 days" },
  { key: "prev_30", label: "Previous 30 days" },
  { key: "prev_3m", label: "Previous 3 months" },
  { key: "next_7", label: "Next 7 days" },
  { key: "next_14", label: "Next 14 days" },
  { key: "next_30", label: "Next 30 days" },
  { key: "next_3m", label: "Next 3 months" },
];

/** A start/finish window: a preset relative to today or to the data date, or
 *  fixed dates (either end may be open). Inclusive at both ends. */
export interface DateRange {
  anchor: DateAnchor;
  preset?: DatePreset;
  from?: string;
  to?: string;
}

export const ACTIVITY_TYPES: { value: string; label: string }[] = [
  { value: "task", label: "Task" },
  { value: "milestone", label: "Milestone" },
  { value: "loe", label: "Level of effort" },
  { value: "wbs", label: "WBS summary" },
];

export const RISK_INDICATORS: { value: string; label: string; hint: string }[] = [
  { value: "critical", label: "Critical path", hint: "Unfinished, zero or negative float" },
  { value: "longest_path", label: "Longest path", hint: "On P6's longest path" },
  { value: "negative_float", label: "Negative float", hint: "Total float below zero" },
  { value: "low_float", label: "Low float", hint: "0 to 10 working days of total float" },
  { value: "overdue_start", label: "Overdue start", hint: "Not started, start before the data date" },
  { value: "overdue_finish", label: "Overdue finish", hint: "Unfinished, finish before the data date" },
  { value: "hard_constraint", label: "Hard constraint", hint: "Mandatory start or finish" },
  { value: "long_duration", label: "Long duration", hint: "More than 44 working days remaining" },
  { value: "future_actual", label: "Actual after data date", hint: "Actual start or finish later than the data date" },
  { value: "high_criticality", label: "High criticality score", hint: "Criticality score of 70 or more" },
];

export interface FilterCriteria {
  statuses: ActivityStatus[];
  wbsId: string | null;
  search: string;
  match: "all" | "any";
  predicates: FilterPredicate[];
  types: string[];
  startRange: DateRange | null;
  finishRange: DateRange | null;
  // An activity matches when it shows ANY of the chosen indicators.
  risks: string[];
  codesInclude: string[];
  codesExclude: string[];
  importantOnly: boolean;
  tags: string[];
}

export const EMPTY_CRITERIA: FilterCriteria = {
  statuses: [],
  wbsId: null,
  search: "",
  match: "all",
  predicates: [],
  types: [],
  startRange: null,
  finishRange: null,
  risks: [],
  codesInclude: [],
  codesExclude: [],
  importantOnly: false,
  tags: [],
};

export interface FilterContext {
  nodeByWbsId: Map<string, WbsNode>;
}

/** What the quick filters need beyond the activity itself. */
export interface FilterEnv {
  dataDate: string | null; // ISO
  // code_value_id -> activity ids; null when codes aren't available (an
  // earlier program, whose activity ids are not the live ones).
  codeMembership: Map<string, Set<string>> | null;
}

function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function todayIso(): string {
  const now = new Date();
  return isoDay(new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())));
}

function shift(iso: string, days: number, months = 0): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (months) d.setUTCMonth(d.getUTCMonth() + months);
  d.setUTCDate(d.getUTCDate() + days);
  return isoDay(d);
}

/** [from, to] (inclusive, ISO days, either end open) a range resolves to. */
export function resolveRange(r: DateRange, dataDate: string | null): [string | null, string | null] {
  if (r.anchor === "fixed") return [r.from || null, r.to || null];
  const anchor = r.anchor === "data_date" ? dataDate?.slice(0, 10) ?? null : todayIso();
  if (!anchor || !r.preset) return [null, null];
  const [dir, size] = r.preset.split("_");
  const sign = dir === "prev" ? -1 : 1;
  const end = size === "3m" ? shift(anchor, 0, 3 * sign) : shift(anchor, Number(size) * sign);
  return sign < 0 ? [end, anchor] : [anchor, end];
}

function inRange(iso: string | null, range: DateRange | null, dataDate: string | null): boolean {
  if (!range) return true;
  const [from, to] = resolveRange(range, dataDate);
  if (!from && !to) return true;
  if (!iso) return false;
  const day = iso.slice(0, 10);
  return (!from || day >= from) && (!to || day <= to);
}

function activityType(a: Activity): string {
  if (a.task_type === START_MILESTONE || a.task_type === FINISH_MILESTONE) return "milestone";
  if (a.task_type === "TT_LOE") return "loe";
  if (a.task_type === "TT_WBS") return "wbs";
  return "task";
}

const HARD_CONSTRAINTS = new Set(["CS_MANDSTART", "CS_MANDFIN"]);

function hasRisk(a: Activity, risk: string, dataDate: string | null): boolean {
  const finished = a.status === "complete" || Boolean(a.actual_finish);
  const tf = toDays(a.total_float_hours, a);
  const dd = dataDate?.slice(0, 10) ?? null;
  switch (risk) {
    case "critical":
      return !finished && Boolean(a.is_critical);
    case "longest_path":
      return Boolean(a.is_longest_path);
    case "negative_float":
      return tf !== null && tf < 0;
    case "low_float":
      return !finished && tf !== null && tf >= 0 && tf <= 10;
    case "overdue_start": {
      const s = displayStart(a);
      return a.status === "not_started" && Boolean(dd && s && s.slice(0, 10) < dd);
    }
    case "overdue_finish": {
      const f = displayFinish(a);
      return !finished && Boolean(dd && f && f.slice(0, 10) < dd);
    }
    case "hard_constraint":
      return HARD_CONSTRAINTS.has(a.constraint_type ?? "") || HARD_CONSTRAINTS.has(a.constraint_type_2 ?? "");
    case "long_duration": {
      const rd = toDays(a.remaining_duration_hours, a);
      return !finished && rd !== null && rd > 44;
    }
    case "future_actual":
      return Boolean(
        dd && ((a.actual_start && a.actual_start.slice(0, 10) > dd) || (a.actual_finish && a.actual_finish.slice(0, 10) > dd)),
      );
    case "high_criticality":
      return (a.criticality_score ?? 0) >= 70;
    default:
      return false;
  }
}

const STATUS_VALUES: { value: string; label: string }[] = [
  { value: "not_started", label: "Not Started" },
  { value: "in_progress", label: "In Progress" },
  { value: "complete", label: "Completed" },
];

function leafNode(a: Activity, ctx: FilterContext): WbsNode | undefined {
  return a.wbs_path ? ctx.nodeByWbsId.get(a.wbs_path) : undefined;
}

export const FIELD_DEFS: FieldDef[] = [
  {
    key: "external_id",
    label: "Activity ID",
    type: "text",
    ops: ["contains", "starts_with", "equals"],
    get: (a) => a.external_id,
  },
  {
    key: "name",
    label: "Activity name",
    type: "text",
    ops: ["contains", "starts_with", "equals"],
    get: (a) => a.name,
  },
  {
    key: "wbs_name",
    label: "WBS name",
    type: "text",
    ops: ["contains", "starts_with", "equals"],
    get: (a, ctx) => leafNode(a, ctx)?.wbs_name ?? "",
  },
  {
    key: "wbs_code",
    label: "WBS code",
    type: "text",
    ops: ["contains", "starts_with", "equals"],
    get: (a, ctx) => leafNode(a, ctx)?.outline_code ?? "",
  },
  {
    key: "discipline",
    label: "Discipline",
    type: "text",
    ops: ["contains", "equals"],
    get: (a) => a.discipline,
  },
  {
    key: "status",
    label: "Status",
    type: "enum",
    ops: ["in"],
    enumValues: STATUS_VALUES,
    get: (a) => a.status,
  },
  {
    key: "is_critical",
    label: "Critical path",
    type: "bool",
    ops: ["is"],
    get: (a) => Boolean(a.is_critical),
  },
  {
    key: "is_longest_path",
    label: "Longest path",
    type: "bool",
    ops: ["is"],
    get: (a) => Boolean(a.is_longest_path),
  },
  {
    key: "total_float_days",
    label: "Total float (days)",
    type: "number",
    ops: ["lte", "gte", "between"],
    get: (a) => toDays(a.total_float_hours, a),
  },
  {
    key: "percent_complete",
    label: "% complete",
    type: "number",
    ops: ["lte", "gte", "between"],
    get: (a) => a.percent_complete ?? 0,
  },
  {
    key: "actual_start",
    label: "Actual start",
    type: "date",
    ops: ["is_empty", "is_set", "before", "after"],
    get: (a) => a.actual_start,
  },
  {
    key: "actual_finish",
    label: "Actual finish",
    type: "date",
    ops: ["is_empty", "is_set", "before", "after"],
    get: (a) => a.actual_finish,
  },
];

export const FIELD_BY_KEY = new Map(FIELD_DEFS.map((f) => [f.key, f]));

function evalPredicate(p: FilterPredicate, a: Activity, ctx: FilterContext): boolean {
  const def = FIELD_BY_KEY.get(p.field);
  if (!def) return true;
  const raw = def.get(a, ctx);

  switch (p.op) {
    case "is_empty":
      return raw == null || raw === "";
    case "is_set":
      return raw != null && raw !== "";
    case "contains":
      return String(raw ?? "").toLowerCase().includes(p.value.toLowerCase());
    case "starts_with":
      return String(raw ?? "").toLowerCase().startsWith(p.value.toLowerCase());
    case "equals":
      return String(raw ?? "").toLowerCase() === p.value.toLowerCase();
    case "in":
      return p.value.split(",").filter(Boolean).includes(String(raw ?? ""));
    case "is":
      return Boolean(raw) === (p.value === "true");
    case "lte":
      return raw != null && Number(raw) <= Number(p.value);
    case "gte":
      return raw != null && Number(raw) >= Number(p.value);
    case "between":
      return raw != null && Number(raw) >= Number(p.value) && Number(raw) <= Number(p.value2 ?? p.value);
    case "before":
      return typeof raw === "string" && raw !== "" && raw < p.value;
    case "after":
      return typeof raw === "string" && raw !== "" && raw > p.value;
    default:
      return true;
  }
}

export function applyFilter(
  activities: Activity[],
  nodeByWbsId: Map<string, WbsNode>,
  criteria: FilterCriteria,
  env: FilterEnv = { dataDate: null, codeMembership: null },
): Activity[] {
  const ctx: FilterContext = { nodeByWbsId };
  const search = criteria.search.trim().toLowerCase();
  const statusSet = new Set(criteria.statuses);
  const typeSet = new Set(criteria.types);
  const tagSet = new Set(criteria.tags);

  const codeSet = (ids: string[]) => {
    if (!env.codeMembership || ids.length === 0) return null;
    const out = new Set<string>();
    for (const id of ids) for (const aid of env.codeMembership.get(id) ?? []) out.add(aid);
    return out;
  };
  const allowed = codeSet(criteria.codesInclude);
  const denied = codeSet(criteria.codesExclude);

  return activities.filter((a) => {
    if (statusSet.size > 0 && !statusSet.has(a.status)) return false;
    if (typeSet.size > 0 && !typeSet.has(activityType(a))) return false;
    if (allowed && !allowed.has(a.id)) return false;
    if (denied && denied.has(a.id)) return false;
    if (criteria.importantOnly && !a.is_important) return false;
    if (tagSet.size > 0 && !(a.tags ?? []).some((t) => tagSet.has(t))) return false;
    if (criteria.risks.length > 0 && !criteria.risks.some((r) => hasRisk(a, r, env.dataDate))) return false;
    if (!inRange(displayStart(a) ?? displayFinish(a), criteria.startRange, env.dataDate)) return false;
    if (!inRange(displayFinish(a) ?? displayStart(a), criteria.finishRange, env.dataDate)) return false;
    if (search && !a.external_id.toLowerCase().includes(search) && !a.name.toLowerCase().includes(search)) {
      return false;
    }
    if (criteria.wbsId) {
      const node = a.wbs_path ? nodeByWbsId.get(a.wbs_path) : undefined;
      if (!node || !node.path_ids.includes(criteria.wbsId)) return false;
    }
    if (criteria.predicates.length > 0) {
      const results = criteria.predicates.map((p) => evalPredicate(p, a, ctx));
      const ok = criteria.match === "all" ? results.every(Boolean) : results.some(Boolean);
      if (!ok) return false;
    }
    return true;
  });
}

/** Client-side upgrade of a stored blob to the current shape. */
export function normalizeCriteria(raw: unknown): FilterCriteria {
  const c = (raw ?? {}) as Partial<FilterCriteria>;
  const strings = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  const range = (v: unknown): DateRange | null => {
    const r = v as DateRange | null | undefined;
    return r && typeof r === "object" && ["today", "data_date", "fixed"].includes(r.anchor) ? r : null;
  };
  return {
    statuses: Array.isArray(c.statuses) ? (c.statuses as ActivityStatus[]) : [],
    wbsId: typeof c.wbsId === "string" ? c.wbsId : null,
    search: typeof c.search === "string" ? c.search : "",
    match: c.match === "any" ? "any" : "all",
    predicates: Array.isArray(c.predicates) ? (c.predicates as FilterPredicate[]) : [],
    types: strings(c.types),
    startRange: range(c.startRange),
    finishRange: range(c.finishRange),
    risks: strings(c.risks),
    codesInclude: strings(c.codesInclude),
    codesExclude: strings(c.codesExclude),
    importantOnly: c.importantOnly === true,
    tags: strings(c.tags),
  };
}

export function criteriaIsEmpty(c: FilterCriteria): boolean {
  return (
    c.statuses.length === 0 &&
    !c.wbsId &&
    !c.search.trim() &&
    c.predicates.length === 0 &&
    c.types.length === 0 &&
    !c.startRange &&
    !c.finishRange &&
    c.risks.length === 0 &&
    c.codesInclude.length === 0 &&
    c.codesExclude.length === 0 &&
    !c.importantOnly &&
    c.tags.length === 0
  );
}
