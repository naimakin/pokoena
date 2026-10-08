"use client";

import type { MouseEvent as ReactMouseEvent } from "react";
import { ExpandIcon } from "@/components/icons";
import { hoursPerDay } from "@/lib/duration";
import type { Activity } from "@/lib/types";
import type { GridRow } from "@/lib/wbs-tree";
import { earliestDate, fmtDate, isGanttMilestone, latestDate, ROW_H, type BaselineDates } from "./model";
import { ZOOM_LEVELS, type Marker, type ScaleSeg, type ZoomKey } from "./useGanttTimeline";

// The Gantt half of Activity Workspace: lenses (what the bars are coloured
// by), the Gantt-only toolbar row, the timescale header and one chart row.

export const LENSES = [
  { key: "progress", label: "Progress" },
  { key: "criticality", label: "Criticality" },
  { key: "variance", label: "Baseline variance" },
] as const;
export type LensKey = (typeof LENSES)[number]["key"];

export function barColor(lens: LensKey, a: Activity, baseline: Map<string, BaselineDates>): string {
  if (lens === "criticality") {
    const tf = a.total_float_hours;
    if (a.is_critical || (tf != null && tf <= 0)) return "var(--crit)";
    if (tf == null) return "var(--info)";
    const days = tf / hoursPerDay(a);
    if (days <= 5) return "var(--warn)";
    if (days <= 20) return "var(--status-active)";
    return "var(--good)";
  }
  if (lens === "variance") {
    const v = baseline.get(a.id)?.finishVar;
    if (v == null) return "var(--info)";
    if (v > 0) return "var(--crit)";
    if (v < 0) return "var(--status-active)";
    return "var(--good)";
  }
  if (a.status === "complete") return "var(--good)";
  if (a.is_critical) return "var(--crit)";
  if (a.status === "in_progress") return "var(--status-active)";
  return "var(--info)";
}

function legendFor(lens: LensKey): { color: string; label: string }[] {
  if (lens === "criticality") {
    return [
      { color: "var(--crit)", label: "Critical (≤0d)" },
      { color: "var(--warn)", label: "≤5d float" },
      { color: "var(--status-active)", label: "≤20d float" },
      { color: "var(--good)", label: ">20d float" },
    ];
  }
  if (lens === "variance") {
    return [
      { color: "var(--crit)", label: "Late vs baseline" },
      { color: "var(--good)", label: "On baseline" },
      { color: "var(--status-active)", label: "Early" },
      { color: "var(--info)", label: "Not in baseline" },
    ];
  }
  return [
    { color: "var(--crit)", label: "Critical" },
    { color: "var(--status-active)", label: "In progress" },
    { color: "var(--info)", label: "Not started" },
    { color: "var(--good)", label: "Complete" },
  ];
}

function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      className={`gantt-toggle${on ? " is-on" : ""}`}
      onClick={() => onChange(!on)}
    >
      <span className="gantt-toggle-track">
        <span className="gantt-toggle-knob" />
      </span>
      {label}
    </button>
  );
}

export interface GanttViewToggles {
  criticalOnly: boolean;
  wbsOnly: boolean;
  milestonesOnly: boolean;
}

/** The second toolbar row, shown only while the Gantt is: bar colouring, the
 *  three view toggles, legend, zoom and Fit. */
export function GanttToolbar({
  lens,
  onLens,
  toggles,
  onToggles,
  zoomKey,
  isFit,
  onZoom,
  onFit,
}: {
  lens: LensKey;
  onLens: (l: LensKey) => void;
  toggles: GanttViewToggles;
  onToggles: (patch: Partial<GanttViewToggles>) => void;
  zoomKey: ZoomKey;
  isFit: boolean;
  onZoom: (k: ZoomKey) => void;
  onFit: () => void;
}) {
  return (
    <div className="gantt-toolbar ws-gantt-toolbar">
      <div className="gantt-radios" role="radiogroup" aria-label="Colour bars by">
        <span className="ws-toolbar-label">Colour by</span>
        {LENSES.map((l) => (
          <label key={l.key} className="gantt-radio">
            <input type="radio" name="ws-gantt-lens" checked={lens === l.key} onChange={() => onLens(l.key)} />
            {l.label}
          </label>
        ))}
      </div>

      <span className="ws-sep" aria-hidden="true" />

      <Toggle label="Critical path only" on={toggles.criticalOnly} onChange={(v) => onToggles({ criticalOnly: v })} />
      <Toggle label="WBS only" on={toggles.wbsOnly} onChange={(v) => onToggles({ wbsOnly: v })} />
      <Toggle label="Milestones only" on={toggles.milestonesOnly} onChange={(v) => onToggles({ milestonesOnly: v })} />

      <div className="spacer" />

      <div className="gantt-legend">
        {legendFor(lens).map(({ color, label }) => (
          <span key={label}>
            <i style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>

      <div className="gantt-zoom" role="group" aria-label="Timescale">
        {ZOOM_LEVELS.map((z) => (
          <button
            key={z.key}
            type="button"
            className={zoomKey === z.key ? "is-on" : undefined}
            aria-pressed={zoomKey === z.key}
            onClick={() => onZoom(z.key)}
          >
            {z.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        title="Zoom so the whole date range fits the chart pane"
        aria-pressed={isFit}
        onClick={onFit}
      >
        <ExpandIcon className="icon" /> Fit
      </button>
    </div>
  );
}

/** The sticky two-tier timescale with the marker flag lane. Drag it to zoom. */
export function GanttScale({
  height,
  width,
  tiers,
  markers,
  onZoomDrag,
}: {
  height: number;
  width: number;
  tiers: { top: ScaleSeg[]; bottom: ScaleSeg[] };
  markers: Marker[];
  onZoomDrag: (e: ReactMouseEvent) => void;
}) {
  return (
    <div
      className="gantt-head gantt-scale"
      style={{ height, width }}
      onMouseDown={onZoomDrag}
      title="Drag the timescale to zoom"
    >
      {/* Coarse tier: the label sticks to the pane's left edge so a long
          year/month stays named while scrolled into. */}
      <div className="gantt-scale-tier is-upper">
        {tiers.top.map((s, i) => (
          <span key={`t${i}`} style={{ left: s.x, width: s.w }}>
            {s.w >= 24 && <em className="gantt-scale-label">{s.label}</em>}
          </span>
        ))}
      </div>
      <div className="gantt-scale-tier is-lower">
        {tiers.bottom.map((s, i) => (
          <span key={`b${i}`} style={{ left: s.x, width: s.w }}>
            {s.w >= s.label.length * 5.5 + 4 ? s.label : ""}
          </span>
        ))}
      </div>
      {/* Flag lane: the labels are pinned inside the sticky scale so they stay
          visible while the rows scroll underneath. */}
      <div className="gantt-scale-tier is-lane" />
      <div className="gantt-marker-labels">
        {markers.map((m, i) => (
          <span
            key={`ml${i}`}
            className={m.kind === "data" ? "gantt-marker-pill is-data" : "gantt-marker-pill"}
            style={{ left: m.x }}
          >
            {m.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/** One row of the chart: current bar, baseline bar, milestone or WBS summary. */
export function ChartRow({
  row,
  idx,
  chartWidth,
  xFor,
  colorOf,
  baselineByActivity,
  bandBaseline,
  showLabels,
  onActivityClick,
}: {
  row: GridRow;
  idx: number;
  chartWidth: number;
  xFor: (ms: number | null | undefined) => number | null;
  colorOf: (a: Activity) => string;
  baselineByActivity: Map<string, BaselineDates>;
  bandBaseline: Map<string, { start: string | null; finish: string | null }>;
  showLabels: boolean;
  onActivityClick?: (a: Activity) => void;
}) {
  function geom(start: string | null, finish: string | null) {
    const x = xFor(start ? new Date(start).getTime() : null);
    const xe = xFor(finish ? new Date(finish).getTime() : null);
    if (x === null || xe === null) return null;
    return { x: Math.max(x, 0), w: Math.max(xe - Math.max(x, 0), 2) };
  }

  if (row.kind === "band") {
    const cur = geom(row.spanStart, row.spanFinish);
    const bl = bandBaseline.get(row.wbsId);
    const base = bl ? geom(bl.start, bl.finish) : null;
    return (
      <div className={`gantt-row is-band d${Math.min(row.depth, 4)}`} style={{ height: ROW_H, width: chartWidth }}>
        {base && <div className="gantt-bar-baseline" style={{ left: base.x, width: base.w }} />}
        {cur && (
          <div className="gantt-bar-summary" style={{ left: cur.x, width: cur.w }}>
            <i style={{ left: 0 }} />
            <i style={{ right: 0 }} />
          </div>
        )}
      </div>
    );
  }

  const a = row.activity;
  const cur = geom(earliestDate(a), latestDate(a));
  const bl = baselineByActivity.get(a.id);
  const base = bl ? geom(bl.start, bl.finish) : null;
  const color = colorOf(a);
  const milestone = isGanttMilestone(a);
  const floatDays = a.total_float_hours != null ? (a.total_float_hours / hoursPerDay(a)).toFixed(1) : "—";
  const title =
    `${a.external_id}: ${a.name}\n` +
    `Current: ${fmtDate(earliestDate(a))} → ${fmtDate(latestDate(a))}\n` +
    (bl ? `Baseline: ${fmtDate(bl.start)} → ${fmtDate(bl.finish)}\n` : "") +
    `Total float: ${floatDays}d · Progress: ${a.percent_complete}%`;

  return (
    <div
      className={`gantt-row${idx % 2 === 0 ? "" : " is-odd"}${onActivityClick ? " is-open" : ""}`}
      style={{ height: ROW_H, width: chartWidth }}
      title={title}
      // The grid row is the keyboard target; this is a mouse convenience.
      onClick={onActivityClick ? () => onActivityClick(a) : undefined}
    >
      {base && !milestone && <div className="gantt-bar-baseline" style={{ left: base.x, width: base.w }} />}
      {cur &&
        (milestone ? (
          <div className="gantt-milestone" style={{ left: cur.x - 6, background: color }} />
        ) : (
          <div
            className="gantt-bar"
            style={{ left: cur.x, width: cur.w, background: color, opacity: a.status === "not_started" ? 0.72 : 1 }}
          >
            {a.status === "in_progress" && a.percent_complete > 0 && (
              <span className="gantt-bar-fill" style={{ width: `${Math.min(a.percent_complete, 100)}%` }} />
            )}
            {showLabels && cur.w > 60 && <span className="gantt-bar-label">{a.name}</span>}
          </div>
        ))}
    </div>
  );
}
