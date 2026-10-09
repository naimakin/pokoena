"use client";

// Semicircle gauge: the arc fills to the actual %, a tick marks the planned %
// (the baseline's, at the data date). When actual trails planned, the stretch
// between them is shaded in the warn / crit soft tone — never the fill itself,
// which keeps its series colour (status lives in text and soft fills, not in
// the series; DESIGN.md).

import type { ReactNode } from "react";
import { fmtPts, ratioTone } from "./viz";

const W = 300;
const H = 140;
const CX = W / 2;
const CY = 128;
const R = 92;
const STROKE = 14;
const LEN = Math.PI * R;

function clamp(v: number): number {
  return Math.min(Math.max(v, 0), 100);
}

function point(pct: number, r = R): [number, number] {
  const theta = Math.PI * (1 - clamp(pct) / 100);
  return [CX + r * Math.cos(theta), CY - r * Math.sin(theta)];
}

function arc(from: number, to: number): string {
  const [x0, y0] = point(from);
  const [x1, y1] = point(to);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${R} ${R} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

export function Gauge({
  actual,
  planned,
  series,
  caption,
  emptyText,
  label,
}: {
  /** % of budget done (may pass 100 — the arc stops at full). */
  actual: number | null;
  /** % the baseline planned by the data date. */
  planned: number | null;
  series: "actual" | "cost";
  caption: ReactNode;
  emptyText: string;
  label: string;
}) {
  const empty = actual == null;
  const tone = ratioTone(actual, planned);
  const behind = !empty && planned != null && actual! < planned && tone !== "good";
  const gap = !empty && planned != null ? actual! - planned : null;

  let planLabel: ReactNode = null;
  if (planned != null) {
    const [tx, ty] = point(planned, R + 22);
    const anchor = planned < 35 ? "end" : planned > 65 ? "start" : "middle";
    planLabel = (
      <text x={tx} y={ty + 4} textAnchor={anchor} className="viz-gauge-plan-label">
        Plan {Math.round(planned * 10) / 10}%
      </text>
    );
  }
  const [pIn, pOut] = planned != null ? [point(planned, R - 11), point(planned, R + 11)] : [null, null];

  return (
    <figure className="viz viz-gauge" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} className="viz-gauge-svg" role="img" aria-hidden="true">
        <path d={arc(0, 100)} className="viz-gauge-track" strokeWidth={STROKE} />
        {!empty && (
          <path
            d={arc(0, 100)}
            className={`viz-gauge-fill is-${series}`}
            strokeWidth={STROKE}
            strokeDasharray={`${(LEN * clamp(actual!)) / 100} ${LEN}`}
          />
        )}
        {behind && (
          <path d={arc(actual!, planned!)} className={`viz-gauge-short is-${tone}`} strokeWidth={STROKE} />
        )}
        {pIn && pOut && (
          <>
            <line x1={pIn[0]} y1={pIn[1]} x2={pOut[0]} y2={pOut[1]} className="viz-gauge-plan-halo" />
            <line x1={pIn[0]} y1={pIn[1]} x2={pOut[0]} y2={pOut[1]} className="viz-gauge-plan" />
          </>
        )}
        {planLabel}
        {/* Beside the arc's ends, clear of the centre caption. */}
        <text x={CX - R - STROKE / 2 - 6} y={CY + 4} textAnchor="end" className="viz-gauge-end">
          0%
        </text>
        <text x={CX + R + STROKE / 2 + 6} y={CY + 4} textAnchor="start" className="viz-gauge-end">
          100%
        </text>
      </svg>
      <figcaption className="viz-gauge-center">
        <span className="viz-gauge-value num">{empty ? "—" : `${Math.round(actual! * 10) / 10}%`}</span>
        <span className="viz-gauge-caption">{empty ? emptyText : caption}</span>
        {gap != null && (
          <span className={`chip chip-${tone === "neutral" ? "neutral" : tone}`}>{fmtPts(gap)} vs plan</span>
        )}
      </figcaption>
    </figure>
  );
}
