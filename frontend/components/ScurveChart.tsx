"use client";

import { useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import type { EvmScurve } from "@/lib/types";
import { InfoIcon } from "@/components/icons";

// Planned Value / Earned Value / Actual Cost cumulative-manhour S-curve.
// Extracted from the EVM page so the Baselines "Baseline vs current" section
// can render the same chart. Gridlines/point markers make the selected
// granularity (daily/weekly/monthly) visibly different in point density, and
// a pointer-hit-tested overlay drives a hover tooltip with exact values —
// there's no chart library in this project, so hit-testing is done by
// mapping pointer position back to the nearest series index.
export function ScurveChart({ series }: { series: EvmScurve["series"] }) {
  const width = 900;
  const height = 260;
  const plotLeft = 54;
  const plotRight = width - 16;
  const plotTop = 40;
  const plotBottom = height - 34;

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const maxValue = Math.max(...series.map((p) => Math.max(p.pv, p.ev, p.ac)), 1);

  function xAt(i: number): number {
    return plotLeft + (i / Math.max(series.length - 1, 1)) * (plotRight - plotLeft);
  }
  function yAt(v: number): number {
    return plotBottom - (v / maxValue) * (plotBottom - plotTop);
  }
  function toPoints(key: "pv" | "ev" | "ac"): string {
    return series.map((p, i) => `${xAt(i)},${yAt(p[key])}`).join(" ");
  }

  function handlePointer(e: ReactPointerEvent<SVGRectElement>) {
    const svg = e.currentTarget.ownerSVGElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * width;
    const frac = (svgX - plotLeft) / (plotRight - plotLeft);
    const idx = Math.max(0, Math.min(series.length - 1, Math.round(frac * (series.length - 1))));
    setHoverIdx(idx);
  }

  const tickEvery = Math.max(1, Math.ceil(series.length / 8));
  const tickIndices = series.map((_, i) => i).filter((i) => i % tickEvery === 0 || i === series.length - 1);
  const showAllMarkers = series.length <= 60;
  const gridFractions = [0, 0.25, 0.5, 0.75, 1];

  const hover = hoverIdx !== null ? series[hoverIdx] : null;

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: "100%", height: "auto", minWidth: 480 }}
        onPointerLeave={() => setHoverIdx(null)}
      >
        {/* horizontal gridlines + value labels */}
        {gridFractions.map((f) => {
          const v = maxValue * f;
          const y = yAt(v);
          return (
            <g key={f}>
              <line x1={plotLeft} y1={y} x2={plotRight} y2={y} stroke="var(--chart-grid)" strokeWidth={1} />
              <text x={plotLeft - 8} y={y + 3} fontSize="9" fill="var(--text-muted)" textAnchor="end">
                {v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)}
              </text>
            </g>
          );
        })}

        {/* vertical ticks + date labels — density visibly reflects the selected granularity */}
        {tickIndices.map((i) => (
          <g key={i}>
            <line x1={xAt(i)} y1={plotTop} x2={xAt(i)} y2={plotBottom} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={xAt(i)} y={plotBottom + 14} fontSize="9" fill="var(--text-muted)" textAnchor="middle">
              {series[i]?.date}
            </text>
          </g>
        ))}

        <polyline points={toPoints("pv")} fill="none" stroke="var(--series-planned)" strokeWidth={2} />
        <polyline points={toPoints("ev")} fill="none" stroke="var(--series-actual)" strokeWidth={2} />
        <polyline points={toPoints("ac")} fill="none" stroke="var(--series-cost)" strokeWidth={2} />

        {showAllMarkers &&
          series.map((p, i) => (
            <g key={i}>
              <circle cx={xAt(i)} cy={yAt(p.pv)} r={1.8} fill="var(--series-planned)" />
              <circle cx={xAt(i)} cy={yAt(p.ev)} r={1.8} fill="var(--series-actual)" />
              <circle cx={xAt(i)} cy={yAt(p.ac)} r={1.8} fill="var(--series-cost)" />
            </g>
          ))}

        {/* transparent hit area for hover/touch inspection */}
        <rect
          x={plotLeft}
          y={plotTop}
          width={plotRight - plotLeft}
          height={plotBottom - plotTop}
          fill="transparent"
          onPointerMove={handlePointer}
          onPointerDown={handlePointer}
        />

        {hover && hoverIdx !== null && (
          <HoverTooltip
            hover={hover}
            x={xAt(hoverIdx)}
            plotTop={plotTop}
            plotBottom={plotBottom}
            plotLeft={plotLeft}
            plotRight={plotRight}
            yAt={yAt}
          />
        )}
      </svg>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", fontSize: ".6875rem", color: "var(--text-muted)", marginTop: ".5rem", flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
          <span style={{ display: "inline-block", width: 14, height: 2, background: "var(--series-planned)" }} /> Planned Value
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
          <span style={{ display: "inline-block", width: 14, height: 2, background: "var(--series-actual)" }} /> Earned Value
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
          <span style={{ display: "inline-block", width: 14, height: 2, background: "var(--series-cost)" }} /> Actual Cost
        </span>
        <span className="info-tip" tabIndex={0}>
          <InfoIcon className="icon" />
          <span className="info-tip-panel">
            Planned Value comes from the locked baseline schedule, Earned Value from reported percent-complete, and
            Actual Cost from submitted progress entries.
          </span>
        </span>
      </div>
    </div>
  );
}

function HoverTooltip({
  hover,
  x,
  plotTop,
  plotBottom,
  plotLeft,
  plotRight,
  yAt,
}: {
  hover: EvmScurve["series"][number];
  x: number;
  plotTop: number;
  plotBottom: number;
  plotLeft: number;
  plotRight: number;
  yAt: (v: number) => number;
}) {
  const boxWidth = 148;
  const boxHeight = 66;
  const highestY = Math.min(yAt(hover.pv), yAt(hover.ev), yAt(hover.ac));

  let boxX = x - boxWidth / 2;
  boxX = Math.max(plotLeft, Math.min(plotRight - boxWidth, boxX));

  let boxY = highestY - boxHeight - 10;
  if (boxY < plotTop) boxY = highestY + 14;

  const rows: Array<[string, number, string]> = [
    ["PV", hover.pv, "var(--series-planned)"],
    ["EV", hover.ev, "var(--series-actual)"],
    ["AC", hover.ac, "var(--series-cost)"],
  ];

  return (
    <g pointerEvents="none">
      <line x1={x} y1={plotTop} x2={x} y2={plotBottom} stroke="var(--border-strong)" strokeWidth={1} strokeDasharray="3 3" />
      {rows.map(([label, v, color]) => (
        <circle key={label} cx={x} cy={yAt(v)} r={3.5} fill={color} stroke="var(--surface)" strokeWidth={1.5} />
      ))}
      <rect
        x={boxX}
        y={boxY}
        width={boxWidth}
        height={boxHeight}
        rx={6}
        fill="var(--surface)"
        stroke="var(--border-strong)"
      />
      <text x={boxX + 8} y={boxY + 14} fontSize="9" fill="var(--text-muted)">
        {hover.date}
      </text>
      {rows.map(([label, v], i) => (
        <text
          key={label}
          x={boxX + 8}
          y={boxY + 30 + i * 13}
          fontSize="9.5"
          fontFamily="var(--font-mono)"
          fill="var(--text-primary)"
        >
          {label} {v.toFixed(1)} MH
        </text>
      ))}
    </g>
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
