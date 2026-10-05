"use client";

// Single-series trend line for the Project Status summary cards — one metric
// (SPI, recovery index, DCMA score) plotted across schedule versions (UPD-n).
// Hand-rolled inline SVG, same idiom as ScurveChart.tsx — no
// chart library in this project.

import type { StatusTrendPoint } from "@/lib/types";

export function TrendLine({
  points,
  color = "var(--dash-1)",
  format = (n: number) => n.toFixed(2),
}: {
  points: StatusTrendPoint[];
  color?: string;
  format?: (n: number) => string;
}) {
  const width = 520;
  const height = 132;
  const padding = 26;

  if (points.length === 0) {
    return <p className="empty-state" style={{ padding: "1.5rem 0" }}>No trend data yet.</p>;
  }

  const last = points[points.length - 1];

  if (points.length === 1) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: ".2rem", padding: ".4rem 0" }}>
        <span className="num" style={{ fontSize: "1.6rem", fontWeight: 700, color }}>
          {format(last.value)}
        </span>
        <span style={{ fontSize: ".6875rem", color: "var(--text-muted)" }}>
          {last.label} · the trend builds as schedule updates are uploaded
        </span>
      </div>
    );
  }

  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const xAt = (i: number) => padding + (i / (points.length - 1)) * (width - padding * 2);
  const yAt = (v: number) =>
    height - padding - ((v - min) / span) * (height - padding * 2);

  const polyline = points.map((p, i) => `${xAt(i)},${yAt(p.value)}`).join(" ");

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Metric trend across schedule versions"
        style={{ width: "100%", height: "auto", minWidth: 280 }}
      >
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border)" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="var(--border)" />
        <polyline
          points={polyline}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle cx={xAt(points.length - 1)} cy={yAt(last.value)} r={3.5} fill={color} />
        <text x={padding} y={padding - 8} fontSize="10" fill="var(--text-muted)">
          {format(max)}
        </text>
        <text x={padding} y={height - padding + 14} fontSize="10" fill="var(--text-muted)">
          {points[0].label}
        </text>
        <text
          x={width - padding}
          y={height - padding + 14}
          fontSize="10"
          fill="var(--text-muted)"
          textAnchor="end"
        >
          {last.label}
        </text>
      </svg>
    </div>
  );
}
