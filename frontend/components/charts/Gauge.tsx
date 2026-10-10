"use client";

// Semicircle gauge: the arc fills to the actual %, a tick marks the planned %
// (the baseline's, at the data date). When actual trails planned, the stretch
// between them is shaded in the warn / crit soft tone — never the fill itself,
// which keeps its series colour (status lives in text and soft fills, not in
// the series; DESIGN.md).
//
// Hover (or keyboard focus): each part of the arc — done, the shortfall, what
// is still to do — lifts and the tooltip reads all of them out as mini bars.

import { useRef, useState, type ReactNode } from "react";
import { fmtPts, ratioTone, tipAt, VizTip, type VizTipRow } from "./viz";

const W = 300;
const H = 140;
const CX = W / 2;
const CY = 128;
const R = 92;
const STROKE = 14;
const LIFT = 4;
const HIT = 30;
const LEN = Math.PI * R;

type Part = "done" | "short" | "rest";

const PART_TITLE: Record<Part, string> = {
  done: "Done to date",
  short: "Behind plan",
  rest: "Still to do",
};

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
  amounts,
}: {
  /** % of budget done (may pass 100 — the arc stops at full). */
  actual: number | null;
  /** % the baseline planned by the data date. */
  planned: number | null;
  series: "actual" | "cost";
  caption: ReactNode;
  emptyText: string;
  label: string;
  /** Formatted amounts behind the %s, for the tooltip ("228k h"). */
  amounts?: { done?: string; planned?: string; rest?: string; total?: string };
}) {
  const boxRef = useRef<HTMLElement>(null);
  const [hover, setHover] = useState<{ part: Part; x: number; y: number; flip: boolean } | null>(null);
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

  const enter = (part: Part) => (e: React.PointerEvent) => {
    if (boxRef.current) setHover({ part, ...tipAt(e, boxRef.current) });
  };
  const leave = () => setHover(null);
  const restFrom = clamp(Math.max(actual ?? 0, behind ? planned! : 0));
  const sw = (part: Part) => STROKE + (hover?.part === part ? LIFT : 0);

  const rows: VizTipRow[] = empty
    ? []
    : [
        {
          swatch: series,
          label: "Actual",
          value: `${(Math.round(actual! * 10) / 10).toFixed(1)}%${amounts?.done ? ` · ${amounts.done}` : ""}`,
          pct: actual,
          markPct: planned,
        },
        ...(planned != null
          ? [
              {
                swatch: "planned",
                label: "Planned by now",
                value: `${planned.toFixed(1)}%${amounts?.planned ? ` · ${amounts.planned}` : ""}`,
                pct: planned,
              },
              { label: "Gap", value: fmtPts(gap), tone },
            ]
          : []),
        {
          swatch: "rest",
          label: "Still to do",
          value: `${(100 - clamp(actual!)).toFixed(1)}%${amounts?.rest ? ` · ${amounts.rest}` : ""}`,
          pct: 100 - clamp(actual!),
        },
      ];

  return (
    <figure
      ref={boxRef}
      className="viz viz-gauge"
      aria-label={label}
      tabIndex={empty ? undefined : 0}
      onFocus={() => !empty && setHover({ part: "done", x: W / 2, y: 20, flip: false })}
      onBlur={leave}
      onPointerLeave={leave}
    >
      <svg viewBox={`0 0 ${W} ${H}`} className="viz-gauge-svg" role="img" aria-hidden="true">
        <path d={arc(0, 100)} className="viz-gauge-track" strokeWidth={STROKE} />
        {!empty && restFrom < 100 && (
          <path
            d={arc(restFrom, 100)}
            className={`viz-gauge-rest${hover?.part === "rest" ? " is-hover" : ""}`}
            strokeWidth={sw("rest")}
          />
        )}
        {!empty && (
          <path
            d={arc(0, 100)}
            className={`viz-gauge-fill is-${series}${hover?.part === "done" ? " is-hover" : ""}`}
            strokeWidth={sw("done")}
            strokeDasharray={`${(LEN * clamp(actual!)) / 100} ${LEN}`}
          />
        )}
        {behind && (
          <path d={arc(actual!, planned!)} className={`viz-gauge-short is-${tone}`} strokeWidth={sw("short")} />
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
        {/* Hit areas wider than the painted arc, one per part. */}
        {!empty && (
          <>
            {actual! > 0 && (
              <path d={arc(0, clamp(actual!))} className="viz-hit" strokeWidth={HIT} onPointerMove={enter("done")} />
            )}
            {behind && (
              <path d={arc(actual!, planned!)} className="viz-hit" strokeWidth={HIT} onPointerMove={enter("short")} />
            )}
            {restFrom < 100 && (
              <path d={arc(restFrom, 100)} className="viz-hit" strokeWidth={HIT} onPointerMove={enter("rest")} />
            )}
          </>
        )}
      </svg>
      <figcaption className="viz-gauge-center">
        <span className="viz-gauge-value num">{empty ? "—" : `${Math.round(actual! * 10) / 10}%`}</span>
        <span className="viz-gauge-caption">{empty ? emptyText : caption}</span>
        {gap != null && (
          <span className={`chip chip-${tone === "neutral" ? "neutral" : tone}`}>{fmtPts(gap)} vs plan</span>
        )}
      </figcaption>
      {hover && !empty && (
        <VizTip
          x={hover.x}
          y={hover.y}
          flip={hover.flip}
          title={
            <>
              {PART_TITLE[hover.part]}
              {amounts?.total ? <span className="viz-tip-sub"> of {amounts.total}</span> : null}
            </>
          }
          rows={rows}
        />
      )}
    </figure>
  );
}
