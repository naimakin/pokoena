// Activity Criticality Score (KS), 0-100 — computed by the backend
// (backend/app/services/criticality.py) and served on every activity:
//
//   KS = 0.40 total float + 0.20 duration share + 0.20 free float/successors
//      + 0.20 site/supply risk
//
// Bands: 80-100 high (daily follow-up), 50-79 medium (weekly), 0-49 low.

import type { Activity, SiteRisk } from "@/lib/types";

export const SITE_RISK_OPTIONS: { value: SiteRisk; label: string; hint: string }[] = [
  { value: "high", label: "High", hint: "Imported material, critical concrete/steel works, weather-dependent" },
  { value: "standard", label: "Standard", hint: "Standard site works, moderate supply risk" },
  { value: "low", label: "Low", hint: "Readily available labor and materials" },
];

export const BREAKDOWN_LABELS: { key: string; label: string; weight: string }[] = [
  { key: "total_float", label: "Total float", weight: "40%" },
  { key: "duration", label: "Duration", weight: "20%" },
  { key: "free_float", label: "Free float / successors", weight: "20%" },
  { key: "site_risk", label: "Site / supply risk", weight: "20%" },
];

export type CriticalityBand = "high" | "medium" | "low";

export function criticalityBand(score: number): CriticalityBand {
  if (score >= 80) return "high";
  if (score >= 50) return "medium";
  return "low";
}

const BAND_CHIP: Record<CriticalityBand, string> = {
  high: "chip-crit",
  medium: "chip-warn",
  low: "chip-good",
};

const BAND_LABEL: Record<CriticalityBand, string> = {
  high: "High — follow up daily",
  medium: "Medium — follow up weekly",
  low: "Low — routine check",
};

export function criticalityChip(a: Pick<Activity, "criticality_score">): string | null {
  return a.criticality_score == null ? null : BAND_CHIP[criticalityBand(a.criticality_score)];
}

export function criticalityLabel(a: Pick<Activity, "criticality_score">): string {
  return a.criticality_score == null ? "—" : `${a.criticality_score} · ${BAND_LABEL[criticalityBand(a.criticality_score)]}`;
}
