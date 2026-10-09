"use client";

// Ring charts: "Time vs work" (two concentric rings — share of the baseline
// span elapsed, share of the work done) and the portfolio's status donut.

import { useState } from "react";
import { fmtPts, ratioTone } from "./viz";

const SIZE = 148;
const C = SIZE / 2;

function ringPath(r: number): string {
  // A full circle starting at 12 o'clock, drawn clockwise.
  return `M${C} ${C - r} a${r} ${r} 0 1 1 0 ${2 * r} a${r} ${r} 0 1 1 0 ${-2 * r}`;
}

function Ring({ r, pct, stroke, cls }: { r: number; pct: number; stroke: number; cls: string }) {
  const len = 2 * Math.PI * r;
  const v = Math.min(Math.max(pct, 0), 100);
  return (
    <>
      <path d={ringPath(r)} className="viz-ring-track" strokeWidth={stroke} />
      {v > 0 && (
        <path
          d={ringPath(r)}
          className={`viz-ring-seg ${cls}`}
          strokeWidth={stroke}
          strokeDasharray={`${(len * v) / 100} ${len}`}
        />
      )}
    </>
  );
}

export function TimeWorkRings({
  elapsed,
  done,
  footnote,
}: {
  elapsed: number | null;
  done: number | null;
  footnote?: string;
}) {
  if (elapsed == null && done == null) {
    return <p className="viz-empty">Needs a baseline with dates and a data date.</p>;
  }
  const gap = elapsed != null && done != null ? done - elapsed : null;
  const tone = ratioTone(done, elapsed);
  return (
    <div className="viz viz-rings">
      <div className="viz-rings-figure">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width={SIZE} height={SIZE} role="img" aria-label="Time elapsed vs work done">
          <Ring r={C - 8} pct={elapsed ?? 0} stroke={12} cls="is-planned" />
          <Ring r={C - 26} pct={done ?? 0} stroke={12} cls="is-actual" />
        </svg>
        <div className="viz-ring-center">
          {/* The number and a small unit — "−20.9 pts" in one size overflows the inner ring. */}
          <span className={`viz-ring-value num tone-${gap == null ? "neutral" : tone}`}>
            {gap == null ? "—" : fmtPts(gap).replace(" pts", "")}
            {gap != null && <small> pts</small>}
          </span>
          <span className="viz-ring-note">
            {gap == null ? "No comparison yet" : gap < 0 ? "Work behind time" : "Work ahead of time"}
          </span>
        </div>
      </div>
      <div className="viz-rings-legend">
        <div className="viz-legend-row">
          <span className="viz-legend-label">
            <i className="viz-key is-planned" aria-hidden="true" />
            Time elapsed
          </span>
          <span className="viz-legend-value num">{elapsed == null ? "—" : `${Math.round(elapsed)}%`}</span>
        </div>
        <div className="viz-legend-row">
          <span className="viz-legend-label">
            <i className="viz-key is-actual" aria-hidden="true" />
            Work done
          </span>
          <span className="viz-legend-value num">{done == null ? "—" : `${Math.round(done * 10) / 10}%`}</span>
        </div>
        {footnote && <div className="viz-foot">{footnote}</div>}
      </div>
    </div>
  );
}

export interface DonutSegment {
  key: string;
  label: string;
  value: number;
  /** CSS class suffix: the colour comes from the stylesheet. */
  tone: string;
}

export function StatusDonut({
  segments,
  centerLabel,
  selected,
  onSelect,
}: {
  segments: DonutSegment[];
  centerLabel: string;
  selected?: string | null;
  onSelect?: (key: string | null) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const total = segments.reduce((n, s) => n + s.value, 0);
  const r = C - 14;
  const len = 2 * Math.PI * r;
  const gap = segments.filter((s) => s.value > 0).length > 1 ? 2 : 0;
  let offset = 0;
  const focus = selected ?? hover;

  return (
    <div className="viz viz-rings">
      <div className="viz-rings-figure">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width={SIZE} height={SIZE} role="img" aria-label={`${total} ${centerLabel}`}>
          <path d={ringPath(r)} className="viz-ring-track" strokeWidth={20} />
          {total > 0 &&
            segments.map((s) => {
              if (s.value <= 0) return null;
              const segLen = (len * s.value) / total;
              const el = (
                <path
                  key={s.key}
                  d={ringPath(r)}
                  className={`viz-ring-seg is-${s.tone}${focus && focus !== s.key ? " is-faded" : ""}`}
                  strokeWidth={focus === s.key ? 24 : 20}
                  strokeDasharray={`${Math.max(segLen - gap, 0.5)} ${len}`}
                  strokeDashoffset={-offset}
                  onMouseEnter={() => setHover(s.key)}
                  onMouseLeave={() => setHover(null)}
                  onClick={onSelect ? () => onSelect(selected === s.key ? null : s.key) : undefined}
                />
              );
              offset += segLen;
              return el;
            })}
        </svg>
        <div className="viz-ring-center">
          <span className="viz-ring-value is-lg num">{total}</span>
          <span className="viz-ring-note">{centerLabel}</span>
        </div>
      </div>
      <div className="viz-rings-legend">
        {segments.map((s) => {
          const body = (
            <>
              <span className="viz-legend-label">
                <i className={`viz-key is-block is-${s.tone}`} aria-hidden="true" />
                {s.label}
              </span>
              <span className="viz-legend-value num">
                {s.value}
                <small>{total > 0 ? ` ${Math.round((s.value / total) * 100)}%` : ""}</small>
              </span>
            </>
          );
          return onSelect ? (
            <button
              key={s.key}
              type="button"
              className={`viz-legend-row is-button${selected === s.key ? " is-on" : ""}`}
              aria-pressed={selected === s.key}
              disabled={s.value === 0}
              onClick={() => onSelect(selected === s.key ? null : s.key)}
              onMouseEnter={() => setHover(s.key)}
              onMouseLeave={() => setHover(null)}
            >
              {body}
            </button>
          ) : (
            <div key={s.key} className="viz-legend-row">
              {body}
            </div>
          );
        })}
      </div>
    </div>
  );
}
