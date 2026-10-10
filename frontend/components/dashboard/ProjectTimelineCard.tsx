"use client";

// The Dashboard's Project Timeline: the Projects Dashboard's timeline row for
// just this project — each month shaded by the criticality of the work active
// in it, with the critical-path strip under it. Click a month for its
// activities (the same drill-down the portfolio uses).

import { useMemo, useState } from "react";
import type { Project, ProjectAnalytics } from "@/lib/types";
import { monthIndex, todayMonthIndex, type PortfolioProject, type ProjectTimeline } from "@/lib/portfolio";
import { PortfolioTimeline } from "@/components/portfolio/PortfolioTimeline";
import { MonthDrill, TimelineLegend } from "@/components/portfolio/PortfolioParts";

type Window = "1y" | "2y" | "all";

const WINDOWS: { key: Window; label: string; months: number | null }[] = [
  { key: "1y", label: "1Y", months: 12 },
  { key: "2y", label: "2Y", months: 24 },
  { key: "all", label: "All", months: null },
];

export function ProjectTimelineCard({
  project,
  timeline,
  analytics,
}: {
  project: Project;
  timeline: ProjectTimeline;
  analytics: ProjectAnalytics | null;
}) {
  const [windowMode, setWindowMode] = useState<Window>("all");
  const [showDensity, setShowDensity] = useState(true);
  const [drill, setDrill] = useState<string | null>(null);

  // The timeline component draws portfolio rows; this is that row's shape for
  // the one project, from what the Dashboard already has.
  const row = useMemo<PortfolioProject>(
    () => ({
      id: project.id,
      name: project.name,
      code: project.code,
      has_schedule: timeline.months.length > 0,
      data_date: analytics?.data_date ?? null,
      activity_count: 0,
      spi: analytics?.spi ?? null,
      planned_pct: analytics?.planned_pct ?? null,
      actual_pct: analytics?.actual_pct ?? null,
      start: null,
      actual_start: null,
      forecast_finish: analytics?.forecast_finish ?? null,
      baseline_finish: analytics?.baseline_finish ?? null,
      finish_variance_days: analytics?.finish_variance_days ?? null,
      quality_score: null,
      progress: "no_data",
      risk: "LOW",
      quality: "LOW",
      critical_count: 0,
      negative_float_count: 0,
      months: timeline.months,
      has_baseline: analytics != null,
      hours: null,
      cost: null,
    }),
    [project, timeline, analytics],
  );

  const range = useMemo<[number, number] | null>(() => {
    const active = timeline.months.filter((m) => m.tasks > 0).map((m) => monthIndex(m.month));
    if (active.length === 0) return null;
    const lo = Math.min(...active);
    const hi = Math.max(...active);
    const span = WINDOWS.find((w) => w.key === windowMode)?.months;
    if (!span || hi - lo + 1 <= span) return [lo, hi];
    // A quarter of the window behind today, the rest ahead — clamped onto the data.
    const start = Math.max(lo, Math.min(todayMonthIndex() - Math.floor(span / 4), hi - span + 1));
    return [start, start + span - 1];
  }, [timeline, windowMode]);

  if (!range) return <p className="viz-empty">No dated work in the programme yet.</p>;

  return (
    <div className="viz-card-body">
      <div className="pf-tl-controls">
        <div className="segmented" role="group" aria-label="Time window">
          {WINDOWS.map((w) => (
            <button
              key={w.key}
              type="button"
              className={windowMode === w.key ? "active" : ""}
              onClick={() => setWindowMode(w.key)}
            >
              {w.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={showDensity}
          className={`gantt-toggle${showDensity ? " is-on" : ""}`}
          onClick={() => setShowDensity((v) => !v)}
        >
          <span className="gantt-toggle-track">
            <span className="gantt-toggle-knob" />
          </span>
          Show density
        </button>
      </div>
      <PortfolioTimeline
        projects={[row]}
        portfolio={[]}
        range={range}
        showDensity={showDensity}
        showPortfolioRow={false}
        onMonthClick={(_p, month) => setDrill(month)}
      />
      {showDensity && <TimelineLegend />}
      {drill && <MonthDrill project={row} month={drill} onClose={() => setDrill(null)} />}
    </div>
  );
}
