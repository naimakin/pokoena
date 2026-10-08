// Presentation metadata for the DCMA 14-Point page: which category a check
// belongs to, what it measures in a sentence, and its target. The targets come
// from the report (`thresholds`): DCMA's own unless the project set its own
// (backend/app/engine/quality/dcma.py::DcmaThresholds, edited on this page).

import type { DcmaCheckResult, DcmaReport } from "@/lib/types";

// "poko" holds POKO's own checks (unscored, `scored: false`); they sit in their
// own section under DCMA's five categories, never in the summary or filters.
export type DcmaCategory = "logic" | "float" | "dates" | "duration" | "performance" | "poko";

export const DCMA_CATEGORIES: { key: DcmaCategory; label: string }[] = [
  { key: "logic", label: "Logic" },
  { key: "float", label: "Float & critical path" },
  { key: "dates", label: "Dates & constraints" },
  { key: "duration", label: "Duration & resources" },
  { key: "performance", label: "Performance" },
];

export function categoryLabel(key: DcmaCategory): string {
  return key === "poko" ? "POKO checks" : DCMA_CATEGORIES.find((c) => c.key === key)?.label ?? "";
}

/** POKO checks list each finding as " / "-separated fields (see the backend). */
export function findingFields(detail: string): string[] {
  return detail.split(" / ");
}

export type Thresholds = Record<string, number>;

/** DCMA's own targets — what an older report without `thresholds` means. */
export const DCMA_DEFAULTS: Thresholds = {
  logic_max: 5,
  leads_max: 0,
  lags_max: 5,
  rel_types_max: 10,
  hard_constraints_max: 5,
  high_float_max: 5,
  high_float_days: 44,
  negative_float_max: 0,
  high_duration_max: 5,
  high_duration_days: 44,
  invalid_dates_max: 0,
  resources_max: 20,
  missed_logic_max: 5,
  cp_length_min: 5,
  cp_length_max: 20,
  zero_float_max: 10,
  bei_min: 0.95,
  bei_max: 1.05,
};

/** One editable number of a check's target. */
export type TargetField = { key: string; label: string; unit: "%" | "days" | "index" };

type CheckMeta = {
  title: string;
  category: DcmaCategory;
  measures: (t: Thresholds) => string;
  target: (t: Thresholds) => string;
  // Where the limit sits on the ring, in % of the whole (two for a band).
  marks: (t: Thresholds) => number[];
  fields: TargetField[];
  /** How over-target reads when it isn't a plain fail. */
  rule?: string;
};

const num = (v: number) => String(Math.round(v * 100) / 100);
const atMost = (key: string) => ({
  target: (t: Thresholds) => (t[key] === 0 ? "None" : `≤ ${num(t[key])}%`),
  marks: (t: Thresholds) => (t[key] > 0 ? [t[key]] : []),
  fields: [{ key, label: "At most", unit: "%" as const }],
});
const text = (s: string) => () => s;

const META: Record<number, CheckMeta> = {
  1: {
    title: "Logic (open ends)",
    category: "logic",
    measures: text("Unfinished activities missing a predecessor or a successor"),
    ...atMost("logic_max"),
  },
  2: { title: "Leads", category: "logic", measures: text("Relationships with a negative lag"), ...atMost("leads_max") },
  3: { title: "Lags", category: "logic", measures: text("Relationships with a positive lag"), ...atMost("lags_max") },
  4: {
    title: "Relationship types",
    category: "logic",
    measures: text("Finish-to-finish and start-to-finish links"),
    ...atMost("rel_types_max"),
    rule: "Warns above half the target, fails above it.",
  },
  5: {
    title: "Hard constraints",
    category: "dates",
    measures: text("Activities with a mandatory start or finish constraint"),
    ...atMost("hard_constraints_max"),
  },
  6: {
    title: "High float",
    category: "float",
    measures: (t) => `Activities with more than ${num(t.high_float_days)} working days of total float`,
    ...atMost("high_float_max"),
    fields: [
      { key: "high_float_max", label: "At most", unit: "%" },
      { key: "high_float_days", label: "High float is over", unit: "days" },
    ],
  },
  7: { title: "Negative float", category: "float", measures: text("Activities with negative total float"), ...atMost("negative_float_max") },
  8: {
    title: "High duration",
    category: "duration",
    measures: (t) => `Activities with more than ${num(t.high_duration_days)} working days remaining`,
    ...atMost("high_duration_max"),
    fields: [
      { key: "high_duration_max", label: "At most", unit: "%" },
      { key: "high_duration_days", label: "High duration is over", unit: "days" },
    ],
  },
  9: {
    title: "Invalid dates",
    category: "dates",
    measures: text("Not-started activities scheduled before the data date"),
    ...atMost("invalid_dates_max"),
  },
  10: {
    title: "Resources",
    category: "duration",
    measures: text("Unfinished activities with no resource assigned"),
    ...atMost("resources_max"),
    rule: "Over target warns; it never fails.",
  },
  11: {
    title: "Missed logic",
    category: "logic",
    measures: text("Completed activities whose successors haven't started"),
    ...atMost("missed_logic_max"),
  },
  12: {
    title: "Critical path length",
    category: "float",
    measures: text("Share of unfinished activities on zero float"),
    target: (t) => `${num(t.cp_length_min)} – ${num(t.cp_length_max)}%`,
    marks: (t) => [t.cp_length_min, t.cp_length_max],
    fields: [
      { key: "cp_length_min", label: "From", unit: "%" },
      { key: "cp_length_max", label: "To", unit: "%" },
    ],
    rule: "Outside the band warns; it never fails.",
  },
  13: {
    title: "Artificial zero float",
    category: "float",
    measures: text("Zero-float activities that aren't on the longest path"),
    ...atMost("zero_float_max"),
    rule: "Over target warns; it never fails.",
  },
  14: {
    title: "Baseline Execution Index",
    category: "performance",
    measures: text("Activities finished vs planned to finish by the data date"),
    target: (t) => `${t.bei_min.toFixed(2)} – ${t.bei_max.toFixed(2)}`,
    marks: (t) => [t.bei_min * 100],
    fields: [
      { key: "bei_min", label: "From", unit: "index" },
      { key: "bei_max", label: "To", unit: "index" },
    ],
    rule: "Within 0.10 outside the band warns; further out fails.",
  },
  15: {
    title: "Out of sequence",
    category: "poko",
    measures: text(
      "Progressed work ahead of its logic: a completed activity with an unfinished FS or FF predecessor, an in-progress one with an unfinished FS or a not-started SS predecessor",
    ),
    // POKO's own rule, not DCMA's: no target to tune — every link is listed.
    target: text("None"),
    marks: () => [],
    fields: [],
    rule: "Any out-of-sequence link warns; it doesn't count toward the score.",
  },
  16: {
    title: "Actuals after data date",
    category: "poko",
    measures: text(
      "Activities with an actual start or actual finish later than the data date — progress recorded in the future",
    ),
    target: text("None"),
    marks: () => [],
    fields: [],
    rule: "Any finding warns; it doesn't count toward the score.",
  },
};

export const CHECK_IDS = Object.keys(META).map(Number);

/** The report's targets, falling back to DCMA's own for any missing. */
export function thresholdsOf(report: DcmaReport | null): Thresholds {
  return { ...DCMA_DEFAULTS, ...(report?.thresholds ?? {}) };
}

export interface ResolvedMeta {
  title: string;
  category: DcmaCategory;
  measures: string;
  target: string;
  marks: number[];
  fields: TargetField[];
  rule?: string;
}

export function metaById(id: number, t: Thresholds = DCMA_DEFAULTS): ResolvedMeta {
  const m = META[id];
  if (!m) return { title: `Check ${id}`, category: "logic", measures: "", target: "—", marks: [], fields: [] };
  return {
    title: m.title,
    category: m.category,
    measures: m.measures(t),
    target: m.target(t),
    marks: m.marks(t),
    fields: m.fields,
    rule: m.rule,
  };
}

export function metaFor(check: DcmaCheckResult, t: Thresholds = DCMA_DEFAULTS): ResolvedMeta {
  const m = metaById(check.id, t);
  return META[check.id] ? m : { ...m, title: check.name };
}

/** Whether any of the check's targets differ from DCMA's. */
export function isCustom(id: number, report: DcmaReport | null): boolean {
  const custom = new Set(report?.customized ?? []);
  return (META[id]?.fields ?? []).some((f) => custom.has(f.key));
}

const BASIS_NOUN: Record<DcmaCheckResult["basis"], string> = {
  activities: "activities",
  relationships: "relationships",
  planned: "planned",
};

export function isIndex(check: DcmaCheckResult): boolean {
  return check.unit === "index";
}

/** The check's headline value: a share, or the index itself for BEI. */
export function resultLabel(check: DcmaCheckResult): string {
  if (check.status === "not_tracked") return "—";
  if (isIndex(check)) return check.value.toFixed(2);
  return `${formatPct(check.pct)}%`;
}

export function formatPct(pct: number): string {
  if (pct === 0) return "0";
  if (pct < 10) return pct.toFixed(1);
  return pct.toFixed(0);
}

/** "37 of 514 activities" — the part over its whole. */
export function countLabel(check: DcmaCheckResult): string {
  if (check.status === "not_tracked") return "Not tracked";
  const part = isIndex(check) ? Math.round(check.value * check.denominator) : check.value;
  const noun = BASIS_NOUN[check.basis] ?? "activities";
  if (isIndex(check)) return `${part} of ${check.denominator} finished`;
  return `${part} of ${check.denominator} ${noun}`;
}

/** The part over its whole without the noun ("37 of 514"), for a slot whose
 *  label already names it — see factLabel. */
export function countShort(check: DcmaCheckResult): string {
  if (check.status === "not_tracked") return "—";
  const part = isIndex(check) ? Math.round(check.value * check.denominator) : check.value;
  return `${part} of ${check.denominator}`;
}

/** The label for countShort. The ring's center already names the whole
 *  (activities / links), so this stays short enough for a narrow card. */
export function factLabel(check: DcmaCheckResult): string {
  return isIndex(check) ? "Finished" : "Affected";
}

/** What the check costs the overall score: the score is the mean of
 *  pass = 1, warn = 0.5, fail = 0 over the applicable checks. */
export function scoreImpact(check: DcmaCheckResult, report: DcmaReport): number {
  if (check.scored === false) return 0;
  const applicable = report.checks.filter((c) => c.scored !== false && c.status !== "not_tracked").length || 1;
  if (check.status === "fail") return -100 / applicable;
  if (check.status === "warn") return -50 / applicable;
  return 0;
}

export const STATUS_LABEL: Record<DcmaCheckResult["status"], string> = {
  pass: "Pass",
  warn: "Warning",
  fail: "Fail",
  not_tracked: "Not tracked",
};

export const STATUS_CHIP: Record<DcmaCheckResult["status"], string> = {
  pass: "chip-good",
  warn: "chip-warn",
  fail: "chip-crit",
  not_tracked: "chip-neutral",
};

/** Ring arc color by status — status tokens only (DESIGN.md). */
export const STATUS_STROKE: Record<DcmaCheckResult["status"], string> = {
  pass: "var(--good)",
  warn: "var(--warn)",
  fail: "var(--crit)",
  not_tracked: "var(--text-tertiary)",
};

export function checksCsv(report: DcmaReport): string {
  const t = thresholdsOf(report);
  const rows = [
    ["#", "Check", "Category", "Status", "Result", "Target", "Affected", "Of", "Basis", "Score impact"],
    ...report.checks.map((c) => {
      const m = metaFor(c, t);
      return [
        String(c.id),
        m.title,
        categoryLabel(m.category),
        STATUS_LABEL[c.status],
        resultLabel(c),
        m.target,
        isIndex(c) ? String(Math.round(c.value * c.denominator)) : String(c.value),
        String(c.denominator),
        c.basis,
        c.scored === false ? "Not scored" : scoreImpact(c, report).toFixed(1),
      ];
    }),
  ];
  return rows.map((r) => r.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(",")).join("\r\n");
}
