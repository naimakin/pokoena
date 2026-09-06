"use client";

// Compact PV / EV / AC line chart for the Dashboard S-curve widget. Hand-rolled
// inline SVG, same idiom as the full chart on the EVM page — no chart library.
// Series colours come from the dashboard theme vars (--dash-1..3).

export interface MiniSCurvePoint {
  date: string;
  pv: number;
  ev: number;
  ac: number;
}

const SERIES: { key: "pv" | "ev" | "ac"; label: string; color: string }[] = [
  { key: "pv", label: "Planned", color: "var(--dash-1)" },
  { key: "ev", label: "Earned", color: "var(--dash-2)" },
  { key: "ac", label: "Actual", color: "var(--dash-3)" },
];

export function MiniSCurve({ series }: { series: MiniSCurvePoint[] }) {
  const width = 640;
  const height = 200;
  const padding = 28;

  if (series.length < 2) {
    return <p className="empty-state">Not enough progress data yet to plot a curve.</p>;
  }

  const maxValue = Math.max(...series.flatMap((p) => [p.pv, p.ev, p.ac]), 1);

  const xAt = (i: number) => padding + (i / (series.length - 1)) * (width - padding * 2);
  const yAt = (v: number) => height - padding - (v / maxValue) * (height - padding * 2);
  const points = (key: "pv" | "ev" | "ac") => series.map((p, i) => `${xAt(i)},${yAt(p[key])}`).join(" ");

  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Planned, earned and actual value over time" style={{ width: "100%", height: "auto", minWidth: 360 }}>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border)" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="var(--border)" />
        {SERIES.map((s) => (
          <polyline key={s.key} points={points(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        <text x={padding} y={padding - 8} fontSize="10" fill="var(--text-muted)">
          {Math.round(maxValue).toLocaleString()} MH
        </text>
        <text x={padding} y={height - padding + 15} fontSize="10" fill="var(--text-muted)">
          {series[0]?.date}
        </text>
        <text x={width - padding} y={height - padding + 15} fontSize="10" fill="var(--text-muted)" textAnchor="end">
          {series[series.length - 1]?.date}
        </text>
      </svg>
      <div className="dash-legend">
        {SERIES.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} /> {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
