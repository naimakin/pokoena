"use client";

// A small axis-free cumulative chart: the baseline budget's planned line and
// the actuals as a filled area, up to the data date. Stretches to its box
// (strokes stay crisp through vector-effect). Hovering shows that month's
// cumulative planned and actual as shares of the budget.

import { useRef, useState } from "react";
import type { ComboMonth } from "./ComboBars";
import { fmtMonthLong, VizTip } from "./viz";

export function Sparkarea({
  months,
  dataDate,
  series,
  budget,
  format,
}: {
  months: ComboMonth[];
  dataDate: string;
  series: "actual" | "cost";
  /** Shares in the tooltip are of this. */
  budget: number;
  format: (v: number) => string;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ i: number; x: number; flip: boolean } | null>(null);
  if (months.length < 2) return null;
  const ddMonth = dataDate.slice(0, 7);
  let cp = 0;
  let ca = 0;
  const pts = months.map((m) => {
    cp += m.planned;
    ca += m.actual;
    return { month: m.month, planned: cp, actual: m.month <= ddMonth ? ca : null };
  });
  const max = Math.max(1e-9, ...pts.map((p) => Math.max(p.planned, p.actual ?? 0)));
  const W = 100;
  const H = 40;
  const x = (i: number) => (i / (pts.length - 1)) * W;
  const y = (v: number) => H - (v / max) * (H - 2) - 1;
  const planned = pts.map((p, i) => `${x(i)},${y(p.planned)}`).join(" ");
  const actualPts = pts
    .map((p, i) => (p.actual == null ? null : ([x(i), y(p.actual)] as const)))
    .filter(Boolean) as (readonly [number, number])[];
  const actualLine = actualPts.map(([a, b]) => `${a},${b}`).join(" ");
  const area = actualPts.length
    ? `M0,${H} ${actualPts.map(([a, b]) => `L${a},${b}`).join(" ")} L${actualPts[actualPts.length - 1][0]},${H} Z`
    : "";
  const ddIdx = months.findIndex((m) => m.month === ddMonth);
  const share = (v: number | null) => (v == null || budget <= 0 ? null : (v / budget) * 100);

  function onMove(e: React.PointerEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1);
    const i = Math.round(frac * (pts.length - 1));
    const px = (i / (pts.length - 1)) * r.width;
    setHover({ i, x: px, flip: px > r.width / 2 });
  }

  const h = hover ? pts[hover.i] : null;
  return (
    <div className="viz viz-spark-box" ref={boxRef} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      <svg className={`viz-spark is-${series}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        {area && <path d={area} className="viz-spark-area" />}
        <polyline points={planned} className="viz-spark-line is-planned" vectorEffect="non-scaling-stroke" />
        {actualLine && (
          <polyline points={actualLine} className="viz-spark-line is-actual" vectorEffect="non-scaling-stroke" />
        )}
        {ddIdx >= 0 && (
          <line x1={x(ddIdx)} x2={x(ddIdx)} y1={0} y2={H} className="viz-spark-dd" vectorEffect="non-scaling-stroke" />
        )}
        {hover && (
          <line
            x1={x(hover.i)}
            x2={x(hover.i)}
            y1={0}
            y2={H}
            className="dash-curve-guide"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
      {h && hover && (
        <VizTip
          x={hover.x}
          y={0}
          flip={hover.flip}
          title={`By end of ${fmtMonthLong(h.month)}`}
          rows={[
            {
              swatch: "planned",
              label: "Planned",
              value: `${format(h.planned)} · ${(share(h.planned) ?? 0).toFixed(0)}%`,
              pct: share(h.planned),
            },
            ...(h.actual != null
              ? [
                  {
                    swatch: series,
                    label: "Actual",
                    value: `${format(h.actual)} · ${(share(h.actual) ?? 0).toFixed(0)}%`,
                    pct: share(h.actual),
                    markPct: share(h.planned),
                  },
                ]
              : []),
          ]}
        />
      )}
    </div>
  );
}
