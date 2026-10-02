// Presentation metadata for the DCMA 14-Point page: which category a check
// belongs to, what it measures in a sentence, its target as a reader states it,
// and where the target sits on the check's ring. The checks themselves (and
// their pass/warn/fail thresholds) live in backend/app/engine/quality/dcma.py —
// keep the targets here in step with that file.

import type { DcmaCheckResult, DcmaReport } from "@/lib/types";

export type DcmaCategory = "logic" | "float" | "dates" | "duration" | "performance";

export const DCMA_CATEGORIES: { key: DcmaCategory; label: string }[] = [
  { key: "logic", label: "Logic" },
  { key: "float", label: "Float & critical path" },
  { key: "dates", label: "Dates & constraints" },
  { key: "duration", label: "Duration & resources" },
  { key: "performance", label: "Performance" },
];

type CheckMeta = {
  title: string;
  category: DcmaCategory;
  measures: string;
  target: string;
  // Where the limit sits on the ring, in % of the whole (two for a band).
  marks: number[];
};

export const DCMA_META: Record<number, CheckMeta> = {
  1: {
    title: "Logic (open ends)",
    category: "logic",
    measures: "Unfinished activities missing a predecessor or a successor",
    target: "≤ 5%",
    marks: [5],
  },
  2: {
    title: "Leads",
    category: "logic",
    measures: "Relationships with a negative lag",
    target: "None",
    marks: [],
  },
  3: {
    title: "Lags",
    category: "logic",
    measures: "Relationships with a positive lag",
    target: "≤ 5%",
    marks: [5],
  },
  4: {
    title: "Relationship types",
    category: "logic",
    measures: "Finish-to-finish and start-to-finish links",
    target: "≤ 10%",
    marks: [10],
  },
  5: {
    title: "Hard constraints",
    category: "dates",
    measures: "Activities with a mandatory start or finish constraint",
    target: "≤ 5%",
    marks: [5],
  },
  6: {
    title: "High float",
    category: "float",
    measures: "Activities with more than 44 working days of total float",
    target: "≤ 5%",
    marks: [5],
  },
  7: {
    title: "Negative float",
    category: "float",
    measures: "Activities with negative total float",
    target: "None",
    marks: [],
  },
  8: {
    title: "High duration",
    category: "duration",
    measures: "Activities with more than 44 working days remaining",
    target: "≤ 5%",
    marks: [5],
  },
  9: {
    title: "Invalid dates",
    category: "dates",
    measures: "Not-started activities scheduled before the data date",
    target: "None",
    marks: [],
  },
  10: {
    title: "Resources",
    category: "duration",
    measures: "Unfinished activities with no resource assigned",
    target: "≤ 20%",
    marks: [20],
  },
  11: {
    title: "Missed logic",
    category: "logic",
    measures: "Completed activities whose successors haven't started",
    target: "≤ 5%",
    marks: [5],
  },
  12: {
    title: "Critical path length",
    category: "float",
    measures: "Share of unfinished activities on zero float",
    target: "5 – 20%",
    marks: [5, 20],
  },
  13: {
    title: "Artificial zero float",
    category: "float",
    measures: "Zero-float activities that aren't on the longest path",
    target: "≤ 10%",
    marks: [10],
  },
  14: {
    title: "Baseline Execution Index",
    category: "performance",
    measures: "Activities finished vs planned to finish by the data date",
    target: "0.95 – 1.05",
    marks: [95],
  },
};

export function metaFor(check: DcmaCheckResult): CheckMeta {
  return (
    DCMA_META[check.id] ?? { title: check.name, category: "logic", measures: "", target: "—", marks: [] }
  );
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
  const applicable = report.checks.filter((c) => c.status !== "not_tracked").length || 1;
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
  const rows = [
    ["#", "Check", "Category", "Status", "Result", "Target", "Affected", "Of", "Basis", "Score impact"],
    ...report.checks.map((c) => {
      const m = metaFor(c);
      return [
        String(c.id),
        m.title,
        DCMA_CATEGORIES.find((k) => k.key === m.category)?.label ?? "",
        STATUS_LABEL[c.status],
        resultLabel(c),
        m.target,
        isIndex(c) ? String(Math.round(c.value * c.denominator)) : String(c.value),
        String(c.denominator),
        c.basis,
        scoreImpact(c, report).toFixed(1),
      ];
    }),
  ];
  return rows.map((r) => r.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(",")).join("\r\n");
}
