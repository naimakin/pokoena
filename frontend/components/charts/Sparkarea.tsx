"use client";

// A small axis-free cumulative chart: the baseline budget's planned line and
// the actuals as a filled area, up to the data date. Stretches to its box
// (strokes stay crisp through vector-effect).

import type { ComboMonth } from "./ComboBars";

export function Sparkarea({
  months,
  dataDate,
  series,
}: {
  months: ComboMonth[];
  dataDate: string;
  series: "actual" | "cost";
}) {
  if (months.length < 2) return null;
  const ddMonth = dataDate.slice(0, 7);
  let cp = 0;
  let ca = 0;
  const pts = months.map((m) => {
    cp += m.planned;
    ca += m.actual;
    return { planned: cp, actual: m.month <= ddMonth ? ca : null };
  });
  const max = Math.max(1e-9, ...pts.map((p) => Math.max(p.planned, p.actual ?? 0)));
  const W = 100;
  const H = 40;
  const x = (i: number) => (i / (pts.length - 1)) * W;
  const y = (v: number) => H - (v / max) * (H - 2) - 1;
  const planned = pts.map((p, i) => `${x(i)},${y(p.planned)}`).join(" ");
  const actualPts = pts.map((p, i) => (p.actual == null ? null : [x(i), y(p.actual)] as const)).filter(Boolean) as (readonly [number, number])[];
  const actualLine = actualPts.map(([a, b]) => `${a},${b}`).join(" ");
  const area = actualPts.length
    ? `M0,${H} ${actualPts.map(([a, b]) => `L${a},${b}`).join(" ")} L${actualPts[actualPts.length - 1][0]},${H} Z`
    : "";
  const ddIdx = months.findIndex((m) => m.month === ddMonth);

  return (
    <svg className={`viz viz-spark is-${series}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      {area && <path d={area} className="viz-spark-area" />}
      <polyline points={planned} className="viz-spark-line is-planned" vectorEffect="non-scaling-stroke" />
      {actualLine && <polyline points={actualLine} className="viz-spark-line is-actual" vectorEffect="non-scaling-stroke" />}
      {ddIdx >= 0 && (
        <line x1={x(ddIdx)} x2={x(ddIdx)} y1={0} y2={H} className="viz-spark-dd" vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  );
}
