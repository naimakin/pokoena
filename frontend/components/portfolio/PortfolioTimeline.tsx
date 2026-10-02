"use client";

// Portfolio Timelines: one row per project, one cell per month. A cell's color
// is the month's criticality density — the summed Criticality Scores of the
// activities active in it (backend/app/services/portfolio.py), placed on five
// quintile steps so projects of any size compare. The thin strip under each
// bar marks the critical path month by month: red where negative-float work
// (delay drivers) is active, amber where zero-float work is, green otherwise.

import { useMemo, useState, type MouseEvent } from "react";
import {
  DENSITY_COLORS,
  DENSITY_LABELS,
  densityCuts,
  densityLevel,
  monthIndex,
  monthKey,
  monthLabel,
  monthShort,
  spiTone,
  todayMonthIndex,
  type PortfolioMonth,
  type PortfolioProject,
} from "@/lib/portfolio";

const LABEL_W = 230;

type Hover = { x: number; y: number; title: string; month: PortfolioMonth; level: number | null; hint: string };

function stripColor(m: PortfolioMonth | undefined): string {
  if (!m || m.tasks === 0) return "transparent";
  if (m.delay_drivers > 0) return "var(--crit)";
  if (m.critical > 0) return "var(--warn)";
  return "var(--good)";
}

export function PortfolioTimeline({
  projects,
  portfolio,
  range,
  showDensity,
  onMonthClick,
}: {
  projects: PortfolioProject[];
  portfolio: PortfolioMonth[];
  range: [number, number]; // inclusive month indexes
  showDensity: boolean;
  onMonthClick: (project: PortfolioProject, month: string) => void;
}) {
  const [hover, setHover] = useState<Hover | null>(null);
  const [lo, hi] = range;
  const count = Math.max(1, hi - lo + 1);
  const columns = `${LABEL_W}px repeat(${count}, minmax(11px, 1fr))`;
  const indexes = useMemo(() => Array.from({ length: count }, (_, i) => lo + i), [lo, count]);

  // Quintiles over every project-month (not just the visible window), so
  // panning the window never recolors a month.
  const projectCuts = useMemo(
    () => densityCuts(projects.flatMap((p) => p.months.map((m) => m.score))),
    [projects],
  );
  const portfolioCuts = useMemo(() => densityCuts(portfolio.map((m) => m.score)), [portfolio]);

  const today = todayMonthIndex();
  const todayVisible = today >= lo && today <= hi;
  const todayFrac = (today - lo + 0.5) / count;
  const todayLeft = `calc(${LABEL_W}px + (100% - ${LABEL_W}px) * ${todayFrac})`;
  const step = count <= 18 ? 1 : count <= 48 ? 3 : count <= 96 ? 6 : 12;

  function cells(months: PortfolioMonth[], cuts: number[], title: string, onClick?: (month: string) => void) {
    const byKey = new Map(months.map((m) => [m.month, m]));
    const span = months.filter((m) => m.tasks > 0).map((m) => monthIndex(m.month));
    const first = span.length ? Math.min(...span) : null;
    const last = span.length ? Math.max(...span) : null;
    return indexes.map((i) => {
      const key = monthKey(i);
      const m = byKey.get(key);
      const inSpan = first !== null && last !== null && i >= first && i <= last;
      if (!inSpan) return <div key={key} className="pf-cell pf-cell-empty" />;
      const month = m ?? { month: key, score: 0, tasks: 0, critical: 0, delay_drivers: 0 };
      const level = month.score > 0 ? densityLevel(month.score, cuts) : null;
      const bg = !showDensity ? "var(--info)" : level === null ? "var(--surface-3)" : DENSITY_COLORS[level];
      const props = {
        className: `pf-cell${i === first ? " is-first" : ""}${i === last ? " is-last" : ""}${onClick ? " is-clickable" : ""}`,
        style: { background: bg },
        "aria-label": `${title}, ${monthLabel(key)}: total score ${month.score}, ${month.tasks} tasks`,
        onMouseMove: (e: MouseEvent) =>
          setHover({
            x: e.clientX,
            y: e.clientY,
            title,
            month,
            level,
            hint: onClick ? "Click for the month's activities" : "",
          }),
        onMouseLeave: () => setHover(null),
      };
      // A div, not a disabled button, where there's nothing to open: browsers
      // don't fire mouse events on a disabled button, so it would lose its tooltip.
      return onClick ? (
        <button key={key} type="button" {...props} onClick={() => onClick(key)} />
      ) : (
        <div key={key} role="img" {...props} />
      );
    });
  }

  /** A note for a project with no work in the window, or null. */
  function outsideWindow(p: PortfolioProject): string | null {
    const active = p.months.filter((m) => m.tasks > 0).map((m) => monthIndex(m.month));
    if (active.length === 0) return null;
    const first = Math.min(...active);
    const last = Math.max(...active);
    if (last < lo) return `Ended ${monthLabel(monthKey(last))} — outside this window`;
    if (first > hi) return `Starts ${monthLabel(monthKey(first))} — outside this window`;
    return null;
  }

  function strip(months: PortfolioMonth[]) {
    const byKey = new Map(months.map((m) => [m.month, m]));
    return indexes.map((i) => (
      <div key={i} className="pf-strip-cell" style={{ background: stripColor(byKey.get(monthKey(i))) }} />
    ));
  }

  return (
    <div className="pf-tl">
      <div className="pf-tl-scroll">
        <div className="pf-tl-inner" style={{ minWidth: LABEL_W + count * 11 }}>
          {/* month axis */}
          <div className="pf-tl-row pf-tl-axis" style={{ gridTemplateColumns: columns }}>
            <div className="pf-tl-label" />
            {indexes.map((i) => {
              const key = monthKey(i);
              const tick = (i - lo) % step === 0;
              return (
                <div key={key} className={`pf-axis-cell${tick ? " is-tick" : ""}`}>
                  {tick && (
                    <span>
                      {monthShort(key)}
                      <br />
                      {key.slice(0, 4)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* portfolio row */}
          <div className="pf-tl-row pf-tl-portfolio" style={{ gridTemplateColumns: columns }}>
            <div className="pf-tl-label">
              <span className="pf-tl-name">Portfolio</span>
              <span className="pf-tl-meta">{projects.length} projects</span>
            </div>
            {cells(portfolio, portfolioCuts, "Portfolio")}
          </div>

          {projects.map((p) => (
            <div key={p.id} className="pf-tl-project">
              <div className="pf-tl-row" style={{ gridTemplateColumns: columns }}>
                <div className="pf-tl-label">
                  <span className="pf-tl-name">{p.name}</span>
                  <span className="pf-tl-meta">
                    <span className="mono">{p.code}</span>
                    {p.has_schedule ? (
                      <>
                        {" · "}Complete <b className="mono">{p.actual_pct?.toFixed(1) ?? "—"}%</b>
                        {" · "}SPI{" "}
                        <b className="mono" style={{ color: spiTone(p.spi) }}>
                          {p.spi?.toFixed(2) ?? "—"}
                        </b>
                      </>
                    ) : (
                      " · No schedule yet"
                    )}
                  </span>
                </div>
                {p.has_schedule && outsideWindow(p) ? (
                  <div className="pf-tl-none" style={{ gridColumn: `2 / span ${count}` }}>
                    {outsideWindow(p)}
                  </div>
                ) : p.has_schedule ? (
                  cells(p.months, projectCuts, p.name, (month) => onMonthClick(p, month))
                ) : (
                  <div className="pf-tl-none" style={{ gridColumn: `2 / span ${count}` }}>
                    Import a programme to see this project here
                  </div>
                )}
              </div>
              {p.has_schedule && showDensity && !outsideWindow(p) && (
                <div className="pf-tl-row pf-tl-strip" style={{ gridTemplateColumns: columns }}>
                  <div className="pf-tl-label" />
                  {strip(p.months)}
                </div>
              )}
            </div>
          ))}

          {todayVisible && (
            <div className={`pf-today${todayFrac > 0.5 ? " is-late" : ""}`} style={{ left: todayLeft }}>
              <span>{monthLabel(monthKey(today))}</span>
            </div>
          )}
        </div>
      </div>

      {hover && (
        <div className="pf-tip" style={{ left: hover.x + 14, top: hover.y + 14 }} role="tooltip">
          <div className="pf-tip-title">
            {hover.title} · {monthLabel(hover.month.month)}
          </div>
          {hover.level !== null && (
            <div className="pf-tip-row">
              <span>Density</span>
              <b>
                <span className="pf-tip-swatch" style={{ background: DENSITY_COLORS[hover.level] }} />
                {DENSITY_LABELS[hover.level]}
              </b>
            </div>
          )}
          <div className="pf-tip-row">
            <span>Total score</span>
            <b className="mono">{hover.month.score.toLocaleString()}</b>
          </div>
          <div className="pf-tip-row">
            <span>Tasks active</span>
            <b className="mono">{hover.month.tasks}</b>
          </div>
          <div className="pf-tip-row">
            <span>Critical (TF ≤ 0)</span>
            <b className="mono">{hover.month.critical}</b>
          </div>
          <div className="pf-tip-row">
            <span>Delay drivers (TF &lt; 0)</span>
            <b className="mono">{hover.month.delay_drivers}</b>
          </div>
          {hover.hint && <div className="pf-tip-hint">{hover.hint}</div>}
        </div>
      )}
    </div>
  );
}
