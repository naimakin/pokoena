// One DCMA check as a ring: the arc is the check's share of its whole (status
// colored), the track is the rest, and a short ink tick on the ring marks the
// limit — so "how much" and "how far past the target" read at a glance. A
// single ratio against a limit, drawn radially: a meter, not a decorative pie.

import type { ReactNode } from "react";

const TAU = Math.PI * 2;

export function DcmaRing({
  pct,
  marks = [],
  stroke,
  size = 112,
  thickness = 9,
  label,
  children,
}: {
  pct: number; // 0–100 (clamped)
  marks?: number[]; // limit positions, in % of the whole
  stroke: string; // a status token, e.g. "var(--crit)"
  size?: number;
  thickness?: number;
  label: string; // accessible name + hover tooltip
  children?: ReactNode; // the center readout
}) {
  const c = size / 2;
  const r = c - thickness / 2 - 4; // room for the limit ticks to overhang
  const circumference = TAU * r;
  const share = Math.max(0, Math.min(100, pct));
  // A sliver still shows: round caps turn a near-zero arc into a dot.
  const arc = share >= 100 ? circumference : share > 0 ? Math.max((share / 100) * circumference, 0.001) : 0;

  return (
    <div className="dcma-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label}>
        <title>{label}</title>
        <circle cx={c} cy={c} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={thickness} />
        {arc > 0 && (
          <circle
            cx={c}
            cy={c}
            r={r}
            fill="none"
            stroke={stroke}
            strokeWidth={thickness}
            strokeLinecap={share >= 100 ? "butt" : "round"}
            strokeDasharray={`${arc} ${circumference}`}
            transform={`rotate(-90 ${c} ${c})`}
            className="dcma-ring-arc"
          />
        )}
        {marks.map((m) => {
          const angle = (Math.min(100, Math.max(0, m)) / 100) * TAU - Math.PI / 2;
          const inner = r - thickness / 2 - 3;
          const outer = r + thickness / 2 + 3;
          const x1 = c + inner * Math.cos(angle);
          const y1 = c + inner * Math.sin(angle);
          const x2 = c + outer * Math.cos(angle);
          const y2 = c + outer * Math.sin(angle);
          return (
            <g key={m}>
              {/* surface halo, so the tick stays legible across the arc */}
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--surface)" strokeWidth={5} strokeLinecap="round" />
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--text-primary)" strokeWidth={2} strokeLinecap="round" />
            </g>
          );
        })}
      </svg>
      {children && <div className="dcma-ring-center">{children}</div>}
    </div>
  );
}
