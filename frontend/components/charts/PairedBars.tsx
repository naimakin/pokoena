"use client";

// Horizontal planned vs actual bars, one row per group (a WBS branch, an
// activity code value, a project). Plain HTML/CSS rather than SVG: rows are
// text-heavy and must ellipsize and wrap like the rest of the page.
//
//   paired — two bars per row, planned above actual (Dashboard).
//   bullet — one actual bar with a planned tick across it (Portfolio, where
//            up to ~40 rows have to stay scannable).
//
// Bars keep their series colours; a row that trails its plan says so in the
// variance text, never by turning the bar red.

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { ratioTone, VizTip } from "./viz";

export interface BarRow {
  key: string;
  label: string;
  /** Planned to date, actual — in the chart's unit. */
  planned: number | null;
  actual: number | null;
  /** Optional track length (e.g. the group's budget) in the same unit. */
  total?: number | null;
  href?: string;
  /** Instead of a link: the label is a button that calls this. */
  onOpen?: () => void;
  /** Extra tooltip rows. */
  details?: { label: string; value: ReactNode }[];
}

export function PairedBars({
  rows,
  max,
  variant = "paired",
  series = "actual",
  format,
  limit,
  showAllLabel,
}: {
  rows: BarRow[];
  /** Axis maximum; defaults to the largest value in view. */
  max?: number;
  variant?: "paired" | "bullet";
  series?: "actual" | "cost";
  format: (v: number | null) => string;
  /** Rows shown before a "Show all" link. */
  limit?: number;
  showAllLabel?: (n: number) => string;
}) {
  const [all, setAll] = useState(false);
  const [tip, setTip] = useState<{ row: BarRow; x: number; y: number; flip: boolean } | null>(null);
  const shown = limit && !all ? rows.slice(0, limit) : rows;
  const axisMax =
    max ??
    Math.max(1e-9, ...rows.map((r) => Math.max(r.planned ?? 0, r.actual ?? 0, r.total ?? 0)));
  const w = (v: number | null | undefined) => `${Math.min(Math.max(((v ?? 0) / axisMax) * 100, 0), 100)}%`;

  /** A value as a share for the tooltip's mini bar: of the row's own budget
   *  when it has one, else of the axis (100 on a % chart). */
  function shareOf(row: BarRow, v: number | null): number | null {
    if (v == null) return null;
    const whole = row.total ?? axisMax;
    return whole > 0 ? (v / whole) * 100 : null;
  }

  function onMove(e: React.MouseEvent<HTMLElement>, row: BarRow) {
    const box = (e.currentTarget.closest(".viz-bars") as HTMLElement).getBoundingClientRect();
    const x = e.clientX - box.left;
    setTip({ row, x, y: e.clientY - box.top + 12, flip: x > box.width / 2 });
  }

  return (
    <div className={`viz viz-bars is-${variant}`} onMouseLeave={() => setTip(null)}>
      {shown.map((r) => {
        const tone = ratioTone(r.actual, r.planned);
        const gap = r.actual != null && r.planned != null ? r.actual - r.planned : null;
        const label = r.onOpen ? (
          <button type="button" className="viz-bars-label is-button" title={r.label} onClick={r.onOpen}>
            {r.label}
          </button>
        ) : r.href ? (
          <Link href={r.href} className="viz-bars-label" title={r.label}>
            {r.label}
          </Link>
        ) : (
          <span className="viz-bars-label" title={r.label}>
            {r.label}
          </span>
        );
        return (
          <div
            key={r.key}
            className={`viz-bars-row${tip?.row.key === r.key ? " is-hover" : ""}`}
            onMouseMove={(e) => onMove(e, r)}
          >
            {label}
            <div className="viz-bars-track" aria-hidden="true">
              {r.total != null && <span className="viz-bars-total" style={{ width: w(r.total) }} />}
              {variant === "paired" ? (
                <>
                  <span className="viz-bar is-planned" style={{ width: w(r.planned) }} />
                  <span className={`viz-bar is-${series}`} style={{ width: w(r.actual) }} />
                </>
              ) : (
                <>
                  <span className={`viz-bar is-${series}`} style={{ width: w(r.actual) }} />
                  {r.planned != null && <span className="viz-bullet-tick" style={{ left: w(r.planned) }} />}
                </>
              )}
            </div>
            <span className="viz-bars-value num">
              <span>
                {format(r.actual)} <span className="viz-bars-of">/ {format(r.planned)}</span>
              </span>
              {gap != null && (
                <span className={`viz-bars-gap${tone === "crit" || tone === "warn" ? ` tone-${tone}` : ""}`}>
                  {gap > 0 ? "+" : gap < 0 ? "−" : ""}
                  {format(Math.abs(gap))}
                </span>
              )}
            </span>
          </div>
        );
      })}
      {limit && rows.length > limit && (
        <button type="button" className="card-link viz-bars-more" onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer" : (showAllLabel?.(rows.length) ?? `Show all ${rows.length}`)}
        </button>
      )}
      {tip && (
        <VizTip
          x={tip.x}
          y={tip.y}
          flip={tip.flip}
          title={tip.row.label}
          rows={[
            {
              swatch: "planned",
              label: "Planned to date",
              value: format(tip.row.planned),
              pct: shareOf(tip.row, tip.row.planned),
            },
            {
              swatch: series,
              label: "Actual",
              value: format(tip.row.actual),
              pct: shareOf(tip.row, tip.row.actual),
              markPct: shareOf(tip.row, tip.row.planned),
            },
            ...(tip.row.planned != null && tip.row.actual != null
              ? [
                  {
                    label: "Variance",
                    value: `${tip.row.actual - tip.row.planned >= 0 ? "+" : "−"}${format(Math.abs(tip.row.actual - tip.row.planned))}`,
                    tone: ratioTone(tip.row.actual, tip.row.planned),
                  },
                ]
              : []),
            ...(tip.row.details ?? []),
          ]}
        />
      )}
    </div>
  );
}
