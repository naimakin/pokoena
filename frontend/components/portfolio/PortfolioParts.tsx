"use client";

// Pieces the Projects Dashboard (portfolio) and the project Dashboard share:
// the most-critical activity table, the timeline's month drill-down and the
// density legend under a timeline.

import { useEffect, useState } from "react";
import { ArrowRightIcon, XIcon } from "@/components/icons";
import { fmtP6Date } from "@/components/reporting/format";
import { api, ApiError } from "@/lib/api";
import { criticalityChip } from "@/lib/criticality";
import {
  DENSITY_COLORS,
  DENSITY_LABELS,
  monthLabel,
  type PortfolioActivity,
  type PortfolioMonth,
  type PortfolioMonthActivities,
} from "@/lib/portfolio";

/** What the month drill-down needs to know about a project. */
export interface TimelineProject {
  id: string;
  name: string;
  code: string;
  months: PortfolioMonth[];
}

export function TimelineLegend() {
  return (
    <div className="pf-legend">
      <span className="pf-legend-title">Density</span>
      {DENSITY_LABELS.map((label, i) => (
        <span key={label} className="pf-legend-item">
          <span className="pf-legend-swatch" style={{ background: DENSITY_COLORS[i] }} />
          {label}
        </span>
      ))}
      <span className="pf-legend-sep" />
      <span className="pf-legend-title">Critical path strip</span>
      <span className="pf-legend-item">
        <span className="pf-legend-bar" style={{ background: "var(--crit)" }} />
        Delay drivers
      </span>
      <span className="pf-legend-item">
        <span className="pf-legend-bar" style={{ background: "var(--warn)" }} />
        Zero float
      </span>
      <span className="pf-legend-item">
        <span className="pf-legend-bar" style={{ background: "var(--good)" }} />
        Float available
      </span>
    </div>
  );
}

export function ActivityTable({ rows, showProject = false }: { rows: PortfolioActivity[]; showProject?: boolean }) {
  if (rows.length === 0) return <p className="empty-state">No unfinished activities.</p>;
  return (
    <div className="table-wrap">
      <table className="pf-table">
        <thead>
          <tr>
            {showProject && <th>Project</th>}
            <th>Activity</th>
            <th>Start</th>
            <th>Finish</th>
            <th style={{ textAlign: "right" }}>Total float</th>
            <th style={{ textAlign: "right" }}>Criticality</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={`${a.project_id}-${a.id}`}>
              {showProject && <td className="mono">{a.project_code}</td>}
              <td>
                <div className="pf-act-name">{a.name}</div>
                <div className="pf-act-id mono">{a.external_id}</div>
              </td>
              <td className="num">{fmtP6Date(a.start)}</td>
              <td className="num">{fmtP6Date(a.finish)}</td>
              <td className="num" style={{ textAlign: "right" }}>
                {a.total_float_days == null ? "—" : `${a.total_float_days.toFixed(1)}d`}
              </td>
              <td style={{ textAlign: "right" }}>
                {a.criticality_score == null ? (
                  <span style={{ color: "var(--text-muted)" }}>—</span>
                ) : (
                  <span className={`chip ${criticalityChip(a)}`} title={breakdownTitle(a)}>
                    {a.criticality_score}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function breakdownTitle(a: PortfolioActivity): string {
  const b = a.criticality_breakdown;
  if (!b) return "";
  return `Total float ${b.total_float} · Duration ${b.duration} · Free float ${b.free_float} · Site risk ${b.site_risk}`;
}

export function MonthDrill({
  project,
  month,
  onClose,
  onOpen,
}: {
  project: TimelineProject;
  month: string;
  onClose: () => void;
  /** "Open <code> dashboard" — left out where you already are on it. */
  onOpen?: () => void;
}) {
  const [data, setData] = useState<PortfolioMonthActivities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<PortfolioMonthActivities>(`/portfolio/projects/${project.id}/months/${month}`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load the month's activities."));
  }, [project.id, month]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const cell = project.months.find((m) => m.month === month);
  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-lg" role="dialog" aria-modal="true" aria-label={`${project.name}, ${monthLabel(month)}`}>
        <div className="modal-head">
          <div>
            <div className="modal-title">
              {project.name} · {monthLabel(month)}
            </div>
            {cell && (
              <div className="card-title-sub">
                Total score {cell.score.toLocaleString()} · {cell.tasks} tasks active · {cell.critical} critical ·{" "}
                {cell.delay_drivers} delay drivers
              </div>
            )}
          </div>
          <button className="act-btn" onClick={onClose} aria-label="Close" title="Close">
            <XIcon className="icon" />
          </button>
        </div>
        <div className="modal-body">
          {error ? (
            <p className="empty-state">{error}</p>
          ) : !data ? (
            <p className="empty-state">Loading…</p>
          ) : (
            <>
              <div className="card-title-sub">
                {data.total > data.activities.length
                  ? `The ${data.activities.length} most critical of ${data.total} activities active this month`
                  : `${data.total} activities active this month, most critical first`}
              </div>
              <ActivityTable rows={data.activities} />
            </>
          )}
        </div>
        <div className="pf-drill-foot">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Close
          </button>
          {onOpen && (
            <button type="button" className="btn btn-primary btn-sm" onClick={onOpen}>
              Open {project.code} dashboard <ArrowRightIcon className="icon" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
