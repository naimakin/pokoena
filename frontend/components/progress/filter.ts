// Client-side activity filter model for the Progress page. The saved-filter
// `criteria` blob the backend stores is exactly `FilterCriteria` (+ a
// `filter_version`); the backend never parses it.

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

export interface FilterCriteria {
  statuses: ActivityStatus[];
  wbsId: string | null;
  search: string;
  match: "all" | "any";
  predicates: FilterPredicate[];
}

export const EMPTY_CRITERIA: FilterCriteria = {
  statuses: [],
  wbsId: null,
  search: "",
  match: "all",
  predicates: [],
};

export interface FilterContext {
  nodeByWbsId: Map<string, WbsNode>;
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
    get: (a) => (a.total_float_hours == null ? null : a.total_float_hours / 8),
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
): Activity[] {
  const ctx: FilterContext = { nodeByWbsId };
  const search = criteria.search.trim().toLowerCase();
  const statusSet = new Set(criteria.statuses);

  return activities.filter((a) => {
    if (statusSet.size > 0 && !statusSet.has(a.status)) return false;
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
  return {
    statuses: Array.isArray(c.statuses) ? (c.statuses as ActivityStatus[]) : [],
    wbsId: typeof c.wbsId === "string" ? c.wbsId : null,
    search: typeof c.search === "string" ? c.search : "",
    match: c.match === "any" ? "any" : "all",
    predicates: Array.isArray(c.predicates) ? (c.predicates as FilterPredicate[]) : [],
  };
}

export function criteriaIsEmpty(c: FilterCriteria): boolean {
  return c.statuses.length === 0 && !c.wbsId && !c.search.trim() && c.predicates.length === 0;
}
