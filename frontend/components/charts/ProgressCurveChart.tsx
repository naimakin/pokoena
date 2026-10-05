"use client";

// Planned vs actual % complete for the Dashboard — GET
// /projects/{id}/evm/progress-curve. Hand-rolled SVG (no chart library in this
// project). Unlike the older viewBox-scaled charts it measures its container
// and draws at 1 SVG unit = 1 CSS pixel, so it keeps a fixed height and 11px
// axis text at any width instead of ballooning on a wide screen.
//
// Series use the semantic tokens of the report's progress block (planned =
// --info, actual = --good, forecast = dashed --good), not the --dash-* theme
// slots — a theme that maps every slot to one hue made the lines unreadable.

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { ProgressCurvePoint } from "@/lib/types";
import { fmtP6Date, fmtPct } from "@/components/reporting/format";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY_MS = 86_400_000;
const PAD_TOP = 26;
const PAD_RIGHT = 14;
const PAD_BOTTOM = 26;
const PAD_LEFT = 42;
const Y_TICKS = [0, 25, 50, 75, 100];
const MONTH_STEPS = [1, 2, 3, 4, 6, 12, 24];
const MIN_TICK_GAP = 68;

interface Row extends ProgressCurvePoint {
  t: number;
}

interface Pt {
  t: number;
  v: number;
}

type SeriesKey = "planned" | "actual" | "forecast";

function chartHeight(width: number): number {
  return width > 0 && width < 480 ? 200 : 240;
}

function seriesOf(rows: Row[], key: SeriesKey): Pt[] {
  const out: Pt[] = [];
  for (const r of rows) {
    const v = r[key];
    if (v != null) out.push({ t: r.t, v });
  }
  return out;
}

/** Month-start ticks between t0 and t1, thinned to at most `maxTicks` on a
 *  calendar-aligned step (quarters land on Jan/Apr/Jul/Oct, etc.). */
function monthTicks(t0: number, t1: number, maxTicks: number): { t: number; label: string }[] {
  const start = new Date(t0);
  let firstIdx = start.getUTCFullYear() * 12 + start.getUTCMonth();
  if (Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1) < t0) firstIdx += 1;
  const all: number[] = [];
  for (let idx = firstIdx; all.length < 1200; idx++) {
    if (Date.UTC(Math.floor(idx / 12), idx % 12, 1) > t1) break;
    all.push(idx);
  }
  const step = MONTH_STEPS.find((s) => Math.ceil(all.length / s) <= maxTicks) ?? 24;
  return all
    .filter((idx) => idx % step === 0)
    .map((idx, i) => {
      const year = Math.floor(idx / 12);
      const month = idx % 12;
      return {
        t: Date.UTC(year, month, 1),
        label: month === 0 || i === 0 ? `${MONTHS[month]} ${year}` : MONTHS[month],
      };
    });
}

/** The values at the data date: planned from the point nearest it, actual from
 *  the latest update. Used when the dashboard summary doesn't carry them. */
export function curveReadout(
  points: ProgressCurvePoint[],
  dataDate: string,
): { planned: number | null; actual: number | null } {
  const dataT = Date.parse(dataDate);
  let planned: number | null = null;
  let plannedDist = Infinity;
  let actual: number | null = null;
  let actualT = -Infinity;
  for (const p of points) {
    const t = Date.parse(p.date);
    if (Number.isNaN(t)) continue;
    if (p.planned != null && !Number.isNaN(dataT) && Math.abs(t - dataT) < plannedDist) {
      plannedDist = Math.abs(t - dataT);
      planned = p.planned;
    }
    if (p.actual != null && t >= actualT) {
      actualT = t;
      actual = p.actual;
    }
  }
  return { planned, actual };
}

const TIP_ROWS: { key: SeriesKey; label: string }[] = [
  { key: "planned", label: "Planned" },
  { key: "actual", label: "Actual" },
  { key: "forecast", label: "Forecast" },
];

export function ProgressCurveChart({ points, dataDate }: { points: ProgressCurvePoint[]; dataDate: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);

  const rows = useMemo<Row[]>(
    () =>
      points
        .map((p) => ({ ...p, t: Date.parse(p.date) }))
        .filter((r) => !Number.isNaN(r.t))
        .sort((a, b) => a.t - b.t),
    [points],
  );
  const plottable = rows.length >= 2;

  const planned = useMemo(() => seriesOf(rows, "planned"), [rows]);
  const actual = useMemo(() => seriesOf(rows, "actual"), [rows]);
  // Forecast starts at the data date; join it to the last actual so the
  // dashed line reads as the continuation of the solid one.
  const forecast = useMemo(() => {
    const f = seriesOf(rows, "forecast");
    const last = actual[actual.length - 1];
    if (last && f.length > 0 && last.t < f[0].t) return [last, ...f];
    return f;
  }, [rows, actual]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.floor(el.clientWidth));
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [plottable]);

  if (!plottable) {
    return <p className="empty-state">Not enough dated points yet to draw a progress curve.</p>;
  }

  const height = chartHeight(width);
  const t0 = rows[0].t;
  const t1 = rows[rows.length - 1].t;
  const span = Math.max(t1 - t0, DAY_MS);
  const plotL = PAD_LEFT;
  const plotR = Math.max(width - PAD_RIGHT, plotL + 1);
  const plotT = PAD_TOP;
  const plotB = height - PAD_BOTTOM;
  const x = (t: number) => plotL + ((t - t0) / span) * (plotR - plotL);
  const y = (v: number) => plotB - (Math.min(Math.max(v, 0), 100) / 100) * (plotB - plotT);
  const path = (pts: Pt[]) =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");

  const dataT = Date.parse(dataDate);
  const ddIn = !Number.isNaN(dataT) && dataT >= t0 && dataT <= t1;
  const ddX = ddIn ? x(dataT) : 0;
  const ddLabelRight = ddX < plotL + (plotR - plotL) * 0.62;
  const ticks = width > 0 ? monthTicks(t0, t1, Math.max(2, Math.floor((plotR - plotL) / MIN_TICK_GAP))) : [];

  function nearest(t: number): number {
    let best = 0;
    let bestDist = Infinity;
    rows.forEach((r, i) => {
      const d = Math.abs(r.t - t);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    return best;
  }

  function onPointer(e: ReactPointerEvent<SVGRectElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0;
    setActive(nearest(t0 + Math.min(Math.max(frac, 0), 1) * span));
  }

  function onKey(e: ReactKeyboardEvent<HTMLDivElement>) {
    const last = rows.length - 1;
    const cur = active ?? nearest(dataT);
    let next: number | null = null;
    if (e.key === "ArrowRight") next = Math.min(last, cur + 1);
    else if (e.key === "ArrowLeft") next = Math.max(0, cur - 1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else if (e.key === "Escape") {
      setActive(null);
      return;
    }
    if (next !== null) {
      e.preventDefault();
      setActive(next);
    }
  }

  const readout = curveReadout(points, dataDate);
  const summaryLabel =
    `Progress curve from ${fmtP6Date(rows[0].date)} to ${fmtP6Date(rows[rows.length - 1].date)}. ` +
    `At the data date ${fmtP6Date(dataDate)}: planned ${fmtPct(readout.planned)}, actual ${fmtPct(readout.actual)}.`;

  const activeRow = active !== null ? rows[active] ?? null : null;
  const activeX = activeRow ? x(activeRow.t) : 0;
  const tipFlip = activeX > plotL + (plotR - plotL) / 2;

  return (
    <div className="dash-curve">
      <div
        ref={wrapRef}
        className="dash-curve-plot"
        style={{ height }}
        tabIndex={0}
        role="group"
        aria-label="Progress curve. Use the left and right arrow keys to step through the dates."
        onKeyDown={onKey}
        onFocus={() => setActive((cur) => cur ?? nearest(dataT))}
        onBlur={() => setActive(null)}
      >
        {width > 0 && (
          <svg
            className="dash-curve-svg"
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={summaryLabel}
          >
            {Y_TICKS.map((v) => (
              <g key={v}>
                <line
                  className={v === 0 ? "dash-curve-base" : "dash-curve-grid"}
                  x1={plotL}
                  x2={plotR}
                  y1={y(v)}
                  y2={y(v)}
                />
                <text x={plotL - 8} y={y(v) + 4} textAnchor="end">
                  {v}%
                </text>
              </g>
            ))}

            {ticks.map((tick) => {
              const tx = x(tick.t);
              const anchor = tx < plotL + 20 ? "start" : tx > plotR - 20 ? "end" : "middle";
              return (
                <g key={tick.t}>
                  <line className="dash-curve-tick" x1={tx} x2={tx} y1={plotB} y2={plotB + 4} />
                  <text x={tx} y={plotB + 17} textAnchor={anchor}>
                    {tick.label}
                  </text>
                </g>
              );
            })}

            {ddIn && (
              <g>
                <line className="dash-curve-dd-line" x1={ddX} x2={ddX} y1={plotT - 6} y2={plotB} />
                <text
                  className="dash-curve-dd"
                  x={ddLabelRight ? ddX + 5 : ddX - 5}
                  y={plotT - 10}
                  textAnchor={ddLabelRight ? "start" : "end"}
                >
                  Data date {fmtP6Date(dataDate)}
                </text>
              </g>
            )}

            {planned.length > 1 && <path className="dash-curve-planned" d={path(planned)} />}
            {forecast.length > 1 && <path className="dash-curve-forecast" d={path(forecast)} />}
            {actual.length > 1 && <path className="dash-curve-actual" d={path(actual)} />}
            {actual.map((p) => (
              <circle key={p.t} className="dash-curve-mark" cx={x(p.t)} cy={y(p.v)} r={3.5} />
            ))}

            {activeRow && (
              <g>
                <line className="dash-curve-guide" x1={activeX} x2={activeX} y1={plotT} y2={plotB} />
                {TIP_ROWS.map(({ key }) => {
                  const v = activeRow[key];
                  return v == null ? null : (
                    <circle key={key} className={`dash-curve-dot is-${key}`} cx={activeX} cy={y(v)} r={4.5} />
                  );
                })}
              </g>
            )}

            <rect
              className="dash-curve-hit"
              x={plotL}
              y={plotT}
              width={plotR - plotL}
              height={plotB - plotT}
              onPointerMove={onPointer}
              onPointerDown={onPointer}
              onPointerLeave={(e) => {
                if (e.pointerType === "mouse") setActive(null);
              }}
            />
          </svg>
        )}

        {activeRow && width > 0 && (
          <div
            className="dash-curve-tip"
            aria-live="polite"
            style={{
              left: tipFlip ? activeX - 12 : activeX + 12,
              top: plotT,
              transform: tipFlip ? "translateX(-100%)" : undefined,
            }}
          >
            <div className="dash-curve-tip-date">
              {fmtP6Date(activeRow.date)}
              {activeRow.t === dataT && " · data date"}
            </div>
            {TIP_ROWS.map(({ key, label }) => {
              const v = activeRow[key];
              return v == null ? null : (
                <div key={key} className="dash-curve-tip-row">
                  <i className={`dash-swatch is-${key}`} />
                  {label}
                  <b className="num">{fmtPct(v)}</b>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="dash-legend">
        <span>
          <i className="dash-swatch is-planned" />
          Planned (baseline)
        </span>
        <span>
          <i className="dash-swatch is-actual" />
          Actual{actual.length > 0 ? ` · ${actual.length} ${actual.length === 1 ? "update" : "updates"}` : ""}
        </span>
        {forecast.length > 0 && (
          <span>
            <i className="dash-swatch is-forecast" />
            Forecast
          </span>
        )}
        {ddIn && (
          <span>
            <i className="dash-swatch is-datadate" />
            Data date
          </span>
        )}
      </div>
    </div>
  );
}
