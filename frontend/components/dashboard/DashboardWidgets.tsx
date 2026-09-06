"use client";

import type { ReactNode } from "react";
import type {
  DashboardSummary,
  DashboardWidgetKey,
  EvmScurve,
  Project,
  ProjectHealth,
  RiskHighlight,
} from "@/lib/types";
import { MiniSCurve } from "@/components/charts/MiniSCurve";
import { CheckIcon, ClockIcon, FlagIcon, UsersIcon } from "@/components/icons";

export interface WidgetContext {
  project: Project;
  summary: DashboardSummary | null;
  health: ProjectHealth | null;
  risks: RiskHighlight[] | null;
  scurve: EvmScurve | null;
  scurveLocked: boolean;
  deadlineDays: number | null;
}

interface WidgetDef {
  title: string;
  description: string;
  span: "kpi" | "half" | "full";
  // true → page wraps the body in card padding; false → widget draws edge-to-edge
  // (tables, lists, self-padded blocks).
  pad?: boolean;
  render: (ctx: WidgetContext) => ReactNode;
}

function Kpi({
  label,
  icon,
  tint,
  children,
  footer,
}: {
  label: string;
  icon: ReactNode;
  tint: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="card kpi">
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        <div className="kpi-icon" style={{ background: `var(--${tint}-soft)`, color: `var(--${tint})` }}>
          {icon}
        </div>
      </div>
      {children}
      {footer}
    </div>
  );
}

export const WIDGET_REGISTRY: Record<DashboardWidgetKey, WidgetDef> = {
  "update-period": {
    title: "Update Period",
    description: "Current period and its status",
    span: "kpi",
    render: ({ summary }) => {
      const status = summary?.active_period_status;
      const deadline = summary?.deadline_at;
      return (
        <Kpi
          label="Update Period"
          tint="good"
          icon={<CheckIcon className="icon" />}
          footer={
            <div className="kpi-sub">
              {deadline ? `Deadline ${new Date(deadline).toLocaleDateString()}` : "No deadline set"}
            </div>
          }
        >
          <div className="kpi-value" style={{ fontSize: "1.4rem" }}>
            {status === "open" ? "Open" : status === "closed" ? "Closed" : "—"}
          </div>
        </Kpi>
      );
    },
  },

  deadline: {
    title: "Deadline Countdown",
    description: "Days until the period closes",
    span: "kpi",
    render: ({ deadlineDays }) => (
      <Kpi
        label="Deadline Countdown"
        tint="warn"
        icon={<ClockIcon className="icon" />}
        footer={<div className="kpi-sub">Until this period closes</div>}
      >
        <div className="kpi-value">
          {deadlineDays ?? "—"}
          {deadlineDays !== null && (
            <span style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-secondary)" }}> days</span>
          )}
        </div>
      </Kpi>
    ),
  },

  "scopes-submitted": {
    title: "Scopes Submitted",
    description: "Subcontractor submission progress",
    span: "kpi",
    render: ({ summary }) => {
      const total = summary?.orgs_total ?? 0;
      const done = summary?.orgs_submitted ?? 0;
      const pct = total > 0 ? Math.round((done / total) * 100) : 0;
      return (
        <Kpi
          label="Scopes Submitted"
          tint="info"
          icon={<UsersIcon className="icon" />}
          footer={
            <div className="progress">
              <span style={{ width: `${pct}%`, background: "var(--info)" }} />
            </div>
          }
        >
          <div className="kpi-value">
            {done}
            <span style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-secondary)" }}> / {total}</span>
          </div>
        </Kpi>
      );
    },
  },

  flagged: {
    title: "Flagged for Review",
    description: "Change requests awaiting a decision",
    span: "kpi",
    render: ({ summary }) => (
      <Kpi
        label="Flagged for Review"
        tint="crit"
        icon={<FlagIcon className="icon" />}
        footer={<div className="kpi-sub">Awaiting admin decision</div>}
      >
        <div className="kpi-value">{summary?.flagged_pending ?? 0}</div>
      </Kpi>
    ),
  },

  "health-badge": {
    title: "Project Health",
    description: "Composite score across schedule, cost and submissions",
    span: "half",
    render: ({ health }) => {
      if (!health) return <p className="empty-state">Health score unavailable.</p>;
      const s = health.status;
      return (
        <div className="health-badge">
          <div className="health-badge-top">
            <div className={`health-grade ${s}`}>{health.grade}</div>
            <div>
              <div className="health-score">
                {health.score ?? "—"}
                {health.score !== null && <small> / 100</small>}
              </div>
              <div className="kpi-sub" style={{ textTransform: "capitalize" }}>
                {s === "unknown" ? "Not enough data" : s}
              </div>
            </div>
          </div>
          <div className="health-factors">
            {health.factors.map((f) => (
              <div key={f.label} className="health-factor">
                <span className={`dot ${f.status}`} />
                <span className="fl">{f.label}</span>
                <span className="fd">{f.detail}</span>
              </div>
            ))}
          </div>
        </div>
      );
    },
  },

  "s-curve": {
    title: "S-Curve",
    description: "Planned vs earned vs actual value",
    span: "full",
    pad: true,
    render: ({ scurve, scurveLocked, project }) => {
      if (scurveLocked) {
        return (
          <p className="empty-state">
            Lock a baseline for <b>{project.name}</b> to see the S-curve.
          </p>
        );
      }
      if (!scurve || scurve.series.length < 2) {
        return <p className="empty-state">No progress recorded against the baseline yet.</p>;
      }
      return (
        <MiniSCurve
          series={scurve.series.map((p) => ({ date: p.date, pv: p.pv, ev: p.ev, ac: p.ac }))}
        />
      );
    },
  },

  "risk-top3": {
    title: "Top Risks",
    description: "Highest-signal schedule and delivery risks",
    span: "half",
    render: ({ risks }) => {
      if (!risks) return <p className="empty-state">Risk highlights unavailable.</p>;
      if (risks.length === 0) return <p className="empty-state">No standout risks right now.</p>;
      return (
        <div className="risk-list">
          {risks.map((r, i) => (
            <div key={`${r.title}-${i}`} className="risk-item">
              <span className={`risk-sev ${r.severity}`} />
              <div>
                <div className="risk-title">{r.title}</div>
                <div className="risk-detail">{r.detail}</div>
                <div className="risk-source">{r.source}</div>
              </div>
            </div>
          ))}
        </div>
      );
    },
  },

  "scope-table": {
    title: "Scope Submission Status",
    description: "Per-subcontractor submission and progress",
    span: "full",
    render: ({ summary }) => (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Subcontractor</th>
              <th>Discipline</th>
              <th>Status</th>
              <th>Activities</th>
              <th>Avg % Complete</th>
            </tr>
          </thead>
          <tbody>
            {summary && summary.scope_status.length > 0 ? (
              summary.scope_status.map((row) => (
                <tr key={row.subcontractor_org_id}>
                  <td>
                    <div className="cell-flex">
                      <div className="subrow-avatar">{row.org_name.slice(0, 2).toUpperCase()}</div>
                      <span className="subname">{row.org_name}</span>
                    </div>
                  </td>
                  <td>{row.discipline}</td>
                  <td>
                    <span className={`chip ${row.submitted ? "chip-good" : "chip-neutral"}`}>
                      {row.submitted ? "Submitted" : "Pending"}
                    </span>
                  </td>
                  <td className="num">{row.activity_count}</td>
                  <td className="num">{row.avg_percent_complete}%</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="empty-state">
                  No subcontractor scopes on this project yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    ),
  },
};

export const WIDGET_ORDER: DashboardWidgetKey[] = [
  "update-period",
  "deadline",
  "scopes-submitted",
  "flagged",
  "health-badge",
  "s-curve",
  "risk-top3",
  "scope-table",
];
