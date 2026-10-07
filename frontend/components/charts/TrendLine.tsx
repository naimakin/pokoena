"use client";

// Single-series trend line for the Project Status summary cards — one metric
// (SPI, recovery index, DCMA score) plotted across schedule versions (UPD-n).
// Hand-rolled inline SVG, same idiom as ScurveChart.tsx — no
// chart library in this project.

import { useState, type PointerEvent } from "react";
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
  // The version under the pointer (or keyboard focus): its value is shown in
  // a tooltip, so the points between the first and the last are readable too.
  const [hover, setHover] = useState<number | null>(null);

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

  function onMove(e: PointerEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * width;
    const i = Math.round(((x - padding) / (width - padding * 2)) * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, i)));
  }

  const tip = hover === null ? null : points[hover];
  const tipText = tip ? `${tip.label}: ${format(tip.value)}` : "";
  const tipW = Math.max(64, tipText.length * 6.2 + 16);
  const tipX = hover === null ? 0 : Math.min(Math.max(xAt(hover) - tipW / 2, 2), width - tipW - 2);
  const tipY = hover === null ? 0 : yAt(points[hover].value) > height / 2 ? padding - 22 : height - padding - 30;

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Metric trend across schedule versions"
        style={{ width: "100%", height: "auto", minWidth: 280, touchAction: "none" }}
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHover(null)}
        tabIndex={0}
        onFocus={() => setHover(points.length - 1)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? points.length - 1) - 1));
          if (e.key === "ArrowRight") setHover((h) => Math.min(points.length - 1, (h ?? 0) + 1));
        }}
      >
        <title>{points.map((p) => `${p.label}: ${format(p.value)}`).join(", ")}</title>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--chart-axis)" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="var(--chart-axis)" />
        <polyline
          points={polyline}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {points.map((p, i) => (
          <circle
            key={`${p.label}-${i}`}
            cx={xAt(i)}
            cy={yAt(p.value)}
            r={i === points.length - 1 || i === hover ? 3.5 : 2.25}
            fill={i === points.length - 1 || i === hover ? color : "var(--surface)"}
            stroke={color}
            strokeWidth={1.5}
          />
        ))}
        {hover !== null && (
          <line
            x1={xAt(hover)}
            x2={xAt(hover)}
            y1={padding}
            y2={height - padding}
            stroke="var(--chart-axis)"
            strokeDasharray="3 3"
          />
        )}
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
        {tip && (
          <g pointerEvents="none">
            <rect x={tipX} y={tipY} width={tipW} height={20} rx={4} fill="var(--text-primary)" opacity={0.92} />
            <text x={tipX + tipW / 2} y={tipY + 14} fontSize="11" fill="var(--surface)" textAnchor="middle">
              {tipText}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
