// Portfolio Dashboard — types for GET /portfolio (backend/app/api/routes/
// portfolio.py) and the timeline's month / density helpers.

import type { AnalyticsMeasure } from "@/lib/types";

export interface PortfolioMonth {
  month: string; // "YYYY-MM"
  score: number; // sum of Criticality Scores of the activities active that month
  tasks: number;
  critical: number; // unfinished, total float <= 0
  delay_drivers: number; // unfinished, negative total float
}

export type ProgressBucket = "ahead" | "on_schedule" | "slightly_behind" | "behind" | "no_data";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type QualityLevel = "HIGH" | "MEDIUM" | "LOW";

export interface PortfolioProject {
  id: string;
  name: string;
  code: string;
  has_schedule: boolean;
  data_date: string | null;
  activity_count: number;
  spi: number | null;
  planned_pct: number | null;
  actual_pct: number | null;
  start: string | null;
  actual_start: string | null;
  forecast_finish: string | null;
  baseline_finish: string | null;
  finish_variance_days: number | null;
  quality_score: number | null;
  progress: ProgressBucket;
  risk: RiskLevel;
  quality: QualityLevel;
  critical_count: number;
  negative_float_count: number;
  months: PortfolioMonth[];
  has_baseline: boolean;
  /** Labor hours, budget vs planned vs actual (services/analytics.py). */
  hours: AnalyticsMeasure | null;
  /** Null when the programme carries no cost. */
  cost: AnalyticsMeasure | null;
}

export interface PortfolioActivity {
  project_id: string;
  project_code: string;
  id: string;
  external_id: string;
  name: string;
  status: string;
  task_type: string | null;
  start: string | null;
  finish: string | null;
  total_float_days: number | null;
  criticality_score: number | null;
  criticality_breakdown: Record<string, number> | null;
}

export interface Portfolio {
  generated_at: string;
  projects: PortfolioProject[];
  months: PortfolioMonth[];
  summary: {
    progress: Record<"ahead" | "on_schedule" | "slightly_behind" | "behind", number>;
    behind_avg_overrun_pct: number | null;
    risk: Record<RiskLevel, number>;
    quality: Record<QualityLevel, number>;
  };
  top_activities: PortfolioActivity[];
  currency: string;
}

export interface PortfolioMonthActivities {
  project_id: string;
  month: string;
  total: number;
  activities: PortfolioActivity[];
}

// --- months ---------------------------------------------------------------------

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function monthIndex(key: string): number {
  return Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1;
}

export function monthKey(index: number): string {
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

export function monthLabel(key: string): string {
  return `${MONTHS[Number(key.slice(5, 7)) - 1]} ${key.slice(0, 4)}`;
}

export function monthShort(key: string): string {
  return MONTHS[Number(key.slice(5, 7)) - 1];
}

export function todayMonthIndex(): number {
  const d = new Date();
  return d.getFullYear() * 12 + d.getMonth();
}

// --- density --------------------------------------------------------------------

// Five steps of the float ramp (DESIGN.md): criticality is float-led — 40% of
// every activity's score is its total float — so its density reads on the
// same green-to-red scale the float badges use. Calm -> hot.
export const DENSITY_COLORS = [
  "var(--float-high)",
  "var(--float-adequate)",
  "var(--float-medium)",
  "var(--float-low)",
  "var(--float-zero)",
];

export const DENSITY_LABELS = ["Very low", "Low", "Moderate", "High", "Very high"];

/** Quintile cut points over a set of month scores (empty months excluded), so
 *  the five colors split the months evenly — comparable across projects of
 *  very different size, where a shared max would paint every small one green. */
export function densityCuts(scores: number[]): number[] {
  const s = scores.filter((x) => x > 0).sort((a, b) => a - b);
  if (s.length === 0) return [1, 1, 1, 1];
  const q = (p: number) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  return [q(0.2), q(0.4), q(0.6), q(0.8)];
}

export function densityLevel(score: number, cuts: number[]): number {
  let level = 0;
  for (const c of cuts) if (score > c) level += 1;
  return Math.min(4, level);
}

// --- verdict presentation --------------------------------------------------------

export const PROGRESS_ROWS: { key: Exclude<ProgressBucket, "no_data">; label: string; tone: string }[] = [
  { key: "ahead", label: "Ahead of schedule", tone: "var(--good)" },
  { key: "on_schedule", label: "On schedule", tone: "var(--good)" },
  { key: "slightly_behind", label: "Slightly behind", tone: "var(--warn)" },
  { key: "behind", label: "Behind schedule", tone: "var(--crit)" },
];

export const RISK_ROWS: { key: RiskLevel; label: string; tone: string }[] = [
  { key: "LOW", label: "Low", tone: "var(--good)" },
  { key: "MEDIUM", label: "Medium", tone: "var(--warn)" },
  { key: "HIGH", label: "High", tone: "var(--crit)" },
];

export const QUALITY_ROWS: { key: QualityLevel; label: string; tone: string }[] = [
  { key: "HIGH", label: "High", tone: "var(--good)" },
  { key: "MEDIUM", label: "Medium", tone: "var(--warn)" },
  { key: "LOW", label: "Low", tone: "var(--crit)" },
];

export const PROGRESS_LABEL: Record<ProgressBucket, string> = {
  ahead: "Ahead",
  on_schedule: "On schedule",
  slightly_behind: "Slightly behind",
  behind: "Behind",
  no_data: "No data",
};

export function spiTone(spi: number | null): string {
  if (spi == null) return "var(--text-tertiary)";
  if (spi >= 0.95) return "var(--good)";
  if (spi >= 0.85) return "var(--warn)";
  return "var(--crit)";
}

export function varianceMonths(days: number | null): string {
  if (days == null) return "";
  const months = days / 30.44;
  if (Math.abs(months) < 0.05) return "On baseline";
  return `${months > 0 ? "+" : "−"}${Math.abs(months).toFixed(1)} months`;
}
