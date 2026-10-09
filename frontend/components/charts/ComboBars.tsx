"use client";

// Monthly planned vs actual bars (left axis, hours or money) with the
// cumulative planned / actual lines over them (right axis, % of budget).
// Bars are the series colours at reduced opacity and the lines full strength
// on top, so the two layers separate by weight rather than by hue. Drawn at
// 1 SVG unit = 1 CSS px, like ProgressCurveChart.

import { useMemo, useState } from "react";
import { fmtMonthLong, fmtMonthShort, useMeasuredWidth, VizTip } from "./viz";

export interface ComboMonth {
  month: string; // "YYYY-MM"
  planned: number;
  actual: number;
}

const PAD_L = 46;
const PAD_R = 42;
const PAD_T = 16;
const PAD_B = 28;

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const mag = 10 ** Math.floor(Math.log10(v));
  const n = v / mag;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * mag;
}

export function ComboBars({
  months,
  budget,
  dataDate,
  series,
  format,
  axisFormat,
}: {
  months: ComboMonth[];
  /** Cumulative lines are drawn as a share of this. */
  budget: number;
  dataDate: string;
  series: "actual" | "cost";
  format: (v: number) => string;
  axisFormat: (v: number) => string;
}) {
  const [wrapRef, width] = useMeasuredWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const ddMonth = dataDate.slice(0, 7);

  const rows = useMemo(() => {
    let cp = 0;
    let ca = 0;
    return months.map((m) => {
      cp += m.planned;
      ca += m.actual;
      const past = m.month <= ddMonth;
      return {
        ...m,
        cumPlanned: budget > 0 ? (cp / budget) * 100 : null,
        cumActual: budget > 0 && past ? (ca / budget) * 100 : null,
        past,
      };
    });
  }, [months, budget, ddMonth]);

  const height = width > 0 && width < 480 ? 220 : 260;
  const n = rows.length;
  const plotL = PAD_L;
  const plotR = Math.max(width - PAD_R, plotL + 1);
  const plotT = PAD_T;
  const plotB = height - PAD_B;
  const band = n > 0 ? (plotR - plotL) / n : 0;
  const barW = Math.max(2, Math.min(12, (band - 6) / 2));
  const yMax = niceMax(Math.max(0, ...rows.map((r) => Math.max(r.planned, r.actual))));
  const y = (v: number) => plotB - (v / yMax) * (plotB - plotT);
  const y2 = (pct: number) => plotB - (Math.min(pct, 120) / 100) * (plotB - plotT);
  const cx = (i: number) => plotL + band * (i + 0.5);
  const labelStep = Math.max(1, Math.ceil(52 / Math.max(band, 1)));
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  const line = (key: "cumPlanned" | "cumActual") =>
    rows
      .map((r, i) => (r[key] == null ? null : `${cx(i).toFixed(1)},${y2(r[key]!).toFixed(1)}`))
      .filter(Boolean)
      .join(" ");

  // Data date: within its month's band, by day of month.
  const ddIdx = rows.findIndex((r) => r.month === ddMonth);
  let ddX: number | null = null;
  if (ddIdx >= 0) {
    const day = Number(dataDate.slice(8, 10)) || 1;
    ddX = plotL + band * (ddIdx + Math.min(day / 31, 1));
  }

  const h = hover != null ? rows[hover] : null;

  return (
    <div className="viz viz-combo" ref={wrapRef}>
      {width > 0 && n > 0 && (
        <svg width={width} height={height} className="viz-svg" role="img" aria-label="Monthly planned vs actual">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={plotL} x2={plotR} y1={y(yMax * t)} y2={y(yMax * t)} className="viz-grid" />
              <text x={plotL - 8} y={y(yMax * t) + 4} textAnchor="end">
                {axisFormat(yMax * t)}
              </text>
              {budget > 0 && (
                <text x={plotR + 8} y={y2(t * 100) + 4} textAnchor="start">
                  {t * 100}%
                </text>
              )}
            </g>
          ))}
          {rows.map((r, i) => (
            <g key={r.month}>
              <rect
                x={cx(i) - barW - 1}
                y={y(r.planned)}
                width={barW}
                height={Math.max(plotB - y(r.planned), 0)}
                className="viz-combo-bar is-planned"
              />
              {r.past && (
                <rect
                  x={cx(i) + 1}
                  y={y(r.actual)}
                  width={barW}
                  height={Math.max(plotB - y(r.actual), 0)}
                  className={`viz-combo-bar is-${series}`}
                />
              )}
              {i % labelStep === 0 && (
                <text x={cx(i)} y={plotB + 18} textAnchor="middle">
                  {fmtMonthShort(r.month)}
                </text>
              )}
            </g>
          ))}
          <line x1={plotL} x2={plotR} y1={plotB} y2={plotB} className="viz-axis" />
          {ddX != null && <line x1={ddX} x2={ddX} y1={plotT} y2={plotB} className="dash-curve-dd-line" />}
          {budget > 0 && (
            <>
              <polyline points={line("cumPlanned")} className="viz-combo-halo" />
              <polyline points={line("cumPlanned")} className="viz-combo-line is-planned" />
              <polyline points={line("cumActual")} className="viz-combo-halo" />
              <polyline points={line("cumActual")} className={`viz-combo-line is-${series}`} />
            </>
          )}
          {h && hover != null && (
            <g>
              <line x1={cx(hover)} x2={cx(hover)} y1={plotT} y2={plotB} className="dash-curve-guide" />
              {h.cumPlanned != null && (
                <circle cx={cx(hover)} cy={y2(h.cumPlanned)} r={3.5} className="dash-curve-dot is-planned" />
              )}
              {h.cumActual != null && (
                <circle cx={cx(hover)} cy={y2(h.cumActual)} r={3.5} className={`viz-dot is-${series}`} />
              )}
            </g>
          )}
          {rows.map((r, i) => (
            <rect
              key={r.month}
              x={plotL + band * i}
              y={plotT}
              width={band}
              height={plotB - plotT}
              className="dash-curve-hit"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>
      )}
      {h && hover != null && (
        <VizTip
          x={cx(hover)}
          y={plotT + 8}
          flip={cx(hover) > width / 2}
          title={fmtMonthLong(h.month)}
          rows={[
            { swatch: "planned", label: "Planned", value: format(h.planned) },
            ...(h.past ? [{ swatch: series, label: "Actual", value: format(h.actual) }] : []),
            ...(h.cumPlanned != null ? [{ label: "Cumulative planned", value: `${h.cumPlanned.toFixed(1)}%` }] : []),
            ...(h.cumActual != null ? [{ label: "Cumulative actual", value: `${h.cumActual.toFixed(1)}%` }] : []),
          ]}
        />
      )}
    </div>
  );
}
