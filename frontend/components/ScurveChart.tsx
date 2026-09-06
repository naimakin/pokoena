"use client";

import type { CSSProperties } from "react";
import type { EvmScurve } from "@/lib/types";

// Planned Value / Earned Value / Actual Cost cumulative-manhour S-curve.
// Extracted from the EVM page so the Baselines "Baseline vs current" section
// can render the same chart.
export function ScurveChart({ series }: { series: EvmScurve["series"] }) {
  const width = 900;
  const height = 220;
  const padding = 32;
  const maxValue = Math.max(...series.map((p) => Math.max(p.pv, p.ev, p.ac)), 1);

  function xAt(i: number): number {
    return padding + (i / Math.max(series.length - 1, 1)) * (width - padding * 2);
  }
  function yAt(v: number): number {
    return height - padding - (v / maxValue) * (height - padding * 2);
  }
  function toPoints(key: "pv" | "ev" | "ac"): string {
    return series.map((p, i) => `${xAt(i)},${yAt(p[key])}`).join(" ");
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", minWidth: 480 }}>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border)" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="var(--border)" />
        <polyline points={toPoints("pv")} fill="none" stroke="var(--info)" strokeWidth={2} />
        <polyline points={toPoints("ev")} fill="none" stroke="var(--good)" strokeWidth={2} />
        <polyline points={toPoints("ac")} fill="none" stroke="var(--accent)" strokeWidth={2} />
        <text x={padding} y={padding - 10} fontSize="10" fill="var(--text-muted)">
          {maxValue.toFixed(0)} MH
        </text>
        <text x={padding} y={height - padding + 16} fontSize="10" fill="var(--text-muted)">
          {series[0]?.date}
        </text>
        <text x={width - padding} y={height - padding + 16} fontSize="10" fill="var(--text-muted)" textAnchor="end">
          {series[series.length - 1]?.date}
        </text>
      </svg>
      <div style={{ display: "flex", gap: "1rem", fontSize: ".6875rem", color: "var(--text-muted)", marginTop: ".5rem" }}>
        <span style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
          <span style={{ display: "inline-block", width: 14, height: 2, background: "var(--info)" }} /> Planned Value
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
          <span style={{ display: "inline-block", width: 14, height: 2, background: "var(--good)" }} /> Earned Value
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
          <span style={{ display: "inline-block", width: 14, height: 2, background: "var(--accent)" }} /> Actual Cost
        </span>
      </div>
    </div>
  );
}

export const selectStyle: CSSProperties = {
  fontSize: ".8125rem",
  height: 32,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};
