"use client";

// Charts for the Risk section. Hand-rolled inline SVG, same idiom as
// ScurveChart.tsx — no chart library in this project. Conventions (from the
// dataviz guidance this was built against):
//   - one y-axis per chart, never two;
//   - colors are existing tokens only: a single series uses --info; a two-series
//     comparison uses --accent / --status-active (the pair clears the CVD and
//     normal-vision separation checks in light and dark); planned/context data
//     is the de-emphasis gray --border-strong; threat/opportunity polarity uses
//     the semantic --warn / --good;
//   - every chart has a legend (for two or more series), a hover/focus
//     tooltip, and its numbers are also in a table on the page — the tooltip
//     never gates a value.

import { useMemo, useState, type PointerEvent as ReactPointerEvent } from "react";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

function fmtMonth(t: number): string {
  const d = new Date(t);
  return `${MONTHS[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(2)}`;
}

const t = (iso: string) => Date.parse(iso.length === 10 ? `${iso}T00:00:00Z` : iso);

export function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function Legend({ items }: { items: { label: string; color: string; kind: "line" | "rect" }[] }) {
  return (
    <div className="risk-legend">
      {items.map((it) => (
        <span key={it.label}>
          {it.kind === "line" ? (
            <i style={{ width: 14, height: 2, background: it.color }} />
          ) : (
            <i style={{ width: 9, height: 9, background: it.color, borderRadius: 2 }} />
          )}
          {it.label}
        </span>
      ))}
    </div>
  );
}

// --- probability of finishing by a date (CDF) -------------------------------------

export interface CdfSeries {
  key: string;
  label: string;
  color: string;
  points: { date: string; pct: number }[];
}

export interface DateMarker {
  date: string;
  label: string;
  tone?: "ink" | "muted" | "accent";
}

export function CdfChart({ series, markers }: { series: CdfSeries[]; markers: DateMarker[] }) {
  const width = 900;
  const height = 280;
  const left = 46;
  const right = width - 18;
  const top = 34;
  const bottom = height - 34;
  const [hoverT, setHoverT] = useState<number | null>(null);

  const allT = [...series.flatMap((s) => s.points.map((p) => t(p.date))), ...markers.map((m) => t(m.date))];
  const minT = Math.min(...allT);
  const maxT = Math.max(...allT);
  const span = maxT - minT || 86400000;
  const pad = span * 0.03;
  const x0 = minT - pad;
  const x1 = maxT + pad;
  const xAt = (v: number) => left + ((v - x0) / (x1 - x0)) * (right - left);
  const yAt = (pct: number) => bottom - (pct / 100) * (bottom - top);

  // Step-after lookup: probability of finishing on or before date v.
  const pctAt = (s: CdfSeries, v: number): number => {
    let out = 0;
    for (const p of s.points) {
      if (t(p.date) <= v) out = p.pct;
      else break;
    }
    return out;
  };

  const ticks = useMemo(() => {
    const out: number[] = [];
    const d = new Date(x0);
    d.setUTCDate(1);
    d.setUTCHours(0, 0, 0, 0);
    const months = Math.max(1, Math.round((x1 - x0) / (30 * 86400000)));
    const step = months > 24 ? 6 : months > 12 ? 3 : months > 5 ? 2 : 1;
    while (d.getTime() <= x1) {
      if (d.getTime() >= x0) out.push(d.getTime());
      d.setUTCMonth(d.getUTCMonth() + step);
    }
    return out;
  }, [x0, x1]);

  function onMove(e: ReactPointerEvent<SVGRectElement>) {
    const svg = e.currentTarget.ownerSVGElement;
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const sx = ((e.clientX - r.left) / r.width) * width;
    const v = x0 + ((sx - left) / (right - left)) * (x1 - x0);
    setHoverT(Math.max(x0, Math.min(x1, v)));
  }

  const markerColor = (tone?: string) =>
    tone === "accent" ? "var(--accent)" : tone === "ink" ? "var(--text-primary)" : "var(--text-muted)";

  return (
    <div className="risk-chart">
      {series.length > 1 && (
        <Legend items={series.map((s) => ({ label: s.label, color: s.color, kind: "line" as const }))} />
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Probability of finishing by each date"
        style={{ width: "100%", height: "auto", minWidth: 420 }}
        onPointerLeave={() => setHoverT(null)}
      >
        {[0, 25, 50, 75, 100].map((g) => (
          <g key={g}>
            <line x1={left} x2={right} y1={yAt(g)} y2={yAt(g)} stroke="var(--border)" />
            <text x={left - 8} y={yAt(g) + 3} fontSize="10" textAnchor="end" fill="var(--text-muted)">
              {g}%
            </text>
          </g>
        ))}
        {ticks.map((tk) => (
          <text key={tk} x={xAt(tk)} y={bottom + 16} fontSize="10" textAnchor="middle" fill="var(--text-muted)">
            {fmtMonth(tk)}
          </text>
        ))}
        {markers.map((m, i) => (
          <g key={`${m.label}-${i}`}>
            <line
              x1={xAt(t(m.date))}
              x2={xAt(t(m.date))}
              y1={top - 6}
              y2={bottom}
              stroke={markerColor(m.tone)}
              strokeWidth={m.tone === "ink" ? 1.5 : 1}
            />
            <text
              x={xAt(t(m.date))}
              y={top - 10 - (i % 2) * 11}
              fontSize="10"
              textAnchor="middle"
              fill="var(--text-secondary)"
              fontWeight={600}
            >
              {m.label}
            </text>
          </g>
        ))}
        {series.map((s) => {
          const pts = s.points.map((p) => `${xAt(t(p.date))},${yAt(p.pct)}`).join(" ");
          return (
            <polyline
              key={s.key}
              points={pts}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}
        {hoverT !== null && (
          <g pointerEvents="none">
            <line x1={xAt(hoverT)} x2={xAt(hoverT)} y1={top} y2={bottom} stroke="var(--text-tertiary)" />
            {series.map((s) => (
              <circle
                key={s.key}
                cx={xAt(hoverT)}
                cy={yAt(pctAt(s, hoverT))}
                r={4}
                fill={s.color}
                stroke="var(--surface)"
                strokeWidth={2}
              />
            ))}
          </g>
        )}
        <rect
          x={left}
          y={top}
          width={right - left}
          height={bottom - top}
          fill="transparent"
          onPointerMove={onMove}
          tabIndex={0}
          aria-label="Move across the chart to read the probability at a date"
          onFocus={() => setHoverT((x0 + x1) / 2)}
          onBlur={() => setHoverT(null)}
        />
      </svg>
      {hoverT !== null && (
        <div
          className="risk-tooltip"
          style={{ left: `${(xAt(hoverT) / width) * 100}%`, top: 8 }}
        >
          <div className="risk-tooltip-title">{fmtDate(new Date(hoverT).toISOString())}</div>
          {series.map((s) => (
            <div key={s.key} className="risk-tooltip-row">
              <i style={{ background: s.color }} />
              <b className="num">{pctAt(s, hoverT).toFixed(0)}%</b>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- histogram ----------------------------------------------------------------------

export function HistogramChart({ bins, bin }: { bins: { date: string; count: number }[]; bin: "day" | "week" }) {
  const width = 900;
  const height = 150;
  const left = 46;
  const right = width - 18;
  const top = 12;
  const bottom = height - 26;
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...bins.map((b) => b.count));
  const total = bins.reduce((s, b) => s + b.count, 0) || 1;
  const slot = (right - left) / Math.max(1, bins.length);
  const barW = Math.min(24, Math.max(2, slot - 2));

  return (
    <div className="risk-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Finish date distribution"
           style={{ width: "100%", height: "auto", minWidth: 420 }} onPointerLeave={() => setHover(null)}>
        <line x1={left} x2={right} y1={bottom} y2={bottom} stroke="var(--border)" />
        {bins.map((b, i) => {
          const h = (b.count / max) * (bottom - top);
          const x = left + i * slot + (slot - barW) / 2;
          return (
            <g key={b.date}>
              <path
                d={`M${x},${bottom} v${-Math.max(h - 2, 0)} q0,-2 2,-2 h${barW - 4} q2,0 2,2 v${Math.max(h - 2, 0)} z`}
                fill="var(--info)"
                opacity={hover === null || hover === i ? 1 : 0.55}
              />
              <rect
                x={left + i * slot}
                y={top}
                width={slot}
                height={bottom - top}
                fill="transparent"
                onPointerMove={() => setHover(i)}
                onFocus={() => setHover(i)}
                tabIndex={-1}
              />
            </g>
          );
        })}
        {bins.length > 0 && (
          <>
            <text x={left} y={bottom + 16} fontSize="10" fill="var(--text-muted)">{fmtDate(bins[0].date)}</text>
            <text x={right} y={bottom + 16} fontSize="10" fill="var(--text-muted)" textAnchor="end">
              {fmtDate(bins[bins.length - 1].date)}
            </text>
          </>
        )}
      </svg>
      {hover !== null && bins[hover] && (
        <div className="risk-tooltip" style={{ left: `${((left + hover * slot + slot / 2) / width) * 100}%`, top: 0 }}>
          <div className="risk-tooltip-title">
            {bin === "week" ? "Week of " : ""}
            {fmtDate(bins[hover].date)}
          </div>
          <div className="risk-tooltip-row">
            <b className="num">{((bins[hover].count / total) * 100).toFixed(1)}%</b>
            <span>of simulated finishes</span>
          </div>
        </div>
      )}
    </div>
  );
}

// --- horizontal bars (tornado / waterfall steps) --------------------------------------

export interface HBarRow {
  key: string;
  label: string;
  sub?: string;
  value: number; // signed
  display: string;
}

export function HBarList({ rows, unit = "days" }: { rows: HBarRow[]; unit?: string }) {
  const max = Math.max(1e-9, ...rows.map((r) => Math.abs(r.value)));
  const hasNegative = rows.some((r) => r.value < 0);
  return (
    <div className="risk-hbars" role="list">
      {rows.map((r) => {
        const pct = (Math.abs(r.value) / max) * (hasNegative ? 50 : 100);
        const color = r.value < 0 ? "var(--good)" : "var(--warn)";
        return (
          <div key={r.key} className="risk-hbar-row" role="listitem" title={`${r.label}: ${r.display} ${unit}`}>
            <div className="risk-hbar-label">
              <span className="subname">{r.label}</span>
              {r.sub && <span className="actid">{r.sub}</span>}
            </div>
            <div className="risk-hbar-track">
              {hasNegative && <span className="risk-hbar-axis" />}
              <span
                className="risk-hbar-fill"
                style={{
                  width: `${pct}%`,
                  background: color,
                  left: hasNegative ? (r.value < 0 ? `${50 - pct}%` : "50%") : 0,
                  borderRadius: r.value < 0 ? "4px 0 0 4px" : "0 4px 4px 0",
                }}
              />
            </div>
            <span className="num risk-hbar-value">{r.display}</span>
          </div>
        );
      })}
    </div>
  );
}

// --- weekly resource chart ---------------------------------------------------------------

export function WeeklyUnitsChart({
  weeks,
  dataDate,
  unit,
}: {
  weeks: { week: string; planned: number; earned: number; actual: number; remaining: number }[];
  dataDate: string;
  unit: string;
}) {
  const width = 900;
  const height = 260;
  const left = 54;
  const right = width - 14;
  const top = 18;
  const bottom = height - 30;
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...weeks.map((w) => Math.max(w.planned, w.earned, w.remaining)));
  const slot = (right - left) / Math.max(1, weeks.length);
  const barW = Math.min(8, Math.max(1.5, (slot - 2) / 3 - 1));
  const series = [
    { key: "planned" as const, label: "Planned", color: "var(--border-strong)" },
    { key: "earned" as const, label: "Earned (averaged per update period)", color: "var(--status-active)" },
    { key: "remaining" as const, label: "Remaining forecast", color: "var(--accent)" },
  ];
  const ddT = t(dataDate);
  const ddIdx = weeks.findIndex((w) => t(w.week) + 7 * 86400000 > ddT);
  const tickEvery = Math.max(1, Math.ceil(weeks.length / 10));
  const gridVals = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);

  return (
    <div className="risk-chart">
      <Legend items={series.map((s) => ({ label: s.label, color: s.color, kind: "rect" as const }))} />
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Units per week"
           style={{ width: "100%", height: "auto", minWidth: 520 }} onPointerLeave={() => setHover(null)}>
        {gridVals.map((g) => {
          const y = bottom - (g / max) * (bottom - top);
          return (
            <g key={g}>
              <line x1={left} x2={right} y1={y} y2={y} stroke="var(--border)" />
              <text x={left - 6} y={y + 3} fontSize="10" textAnchor="end" fill="var(--text-muted)">
                {fmtNum(g)}
              </text>
            </g>
          );
        })}
        {weeks.map((w, i) => {
          const x0 = left + i * slot + (slot - (barW * 3 + 2)) / 2;
          return (
            <g key={w.week}>
              {series.map((s, k) => {
                const v = w[s.key];
                const h = (v / max) * (bottom - top);
                if (h <= 0) return null;
                return (
                  <rect
                    key={s.key}
                    x={x0 + k * (barW + 1)}
                    y={bottom - h}
                    width={barW}
                    height={h}
                    rx={Math.min(2, barW / 2)}
                    fill={s.color}
                    opacity={hover === null || hover === i ? 1 : 0.5}
                  />
                );
              })}
              {i % tickEvery === 0 && (
                <text x={left + i * slot + slot / 2} y={bottom + 16} fontSize="10" textAnchor="middle"
                      fill="var(--text-muted)">
                  {fmtMonth(t(w.week))}
                </text>
              )}
              <rect x={left + i * slot} y={top} width={slot} height={bottom - top} fill="transparent"
                    onPointerMove={() => setHover(i)} />
            </g>
          );
        })}
        {ddIdx >= 0 && (
          <g>
            <line x1={left + ddIdx * slot} x2={left + ddIdx * slot} y1={top - 4} y2={bottom} stroke="var(--accent)" />
            <text x={left + ddIdx * slot + 4} y={top + 6} fontSize="10" fill="var(--text-secondary)" fontWeight={600}>
              Data date
            </text>
          </g>
        )}
      </svg>
      {hover !== null && weeks[hover] && (
        <div className="risk-tooltip" style={{ left: `${((left + hover * slot + slot / 2) / width) * 100}%`, top: 24 }}>
          <div className="risk-tooltip-title">Week of {fmtDate(weeks[hover].week)}</div>
          {series.map((s) => (
            <div key={s.key} className="risk-tooltip-row">
              <i style={{ background: s.color }} />
              <b className="num">{fmtNum(weeks[hover][s.key])}</b>
              <span>{s.label.replace(" (averaged per update period)", "")}</span>
            </div>
          ))}
          {weeks[hover].actual > 0 && (
            <div className="risk-tooltip-row">
              <i style={{ background: "transparent" }} />
              <b className="num">{fmtNum(weeks[hover].actual)}</b>
              <span>Actual burned</span>
            </div>
          )}
          <div className="risk-tooltip-foot">{unit}/week</div>
        </div>
      )}
    </div>
  );
}

// --- sparkline --------------------------------------------------------------------------

export function Sparkline({ values }: { values: number[] }) {
  const w = 120;
  const h = 32;
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${2 + (i / (values.length - 1)) * (w - 6)},${h - 3 - ((v - min) / span) * (h - 8)}`);
  const last = pts[pts.length - 1].split(",").map(Number);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden="true">
      <polyline points={pts.join(" ")} fill="none" stroke="var(--text-tertiary)" strokeWidth={1.5}
                strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={3} fill="var(--accent)" stroke="var(--surface)" strokeWidth={1.5} />
    </svg>
  );
}
