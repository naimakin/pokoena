"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import type {
  CurrentUpdate,
  DashboardSummary,
  DashboardWidgetKey,
  HealthFactorKey,
  HealthStatus,
  ProgressCurve,
  Project,
  ProjectAnalytics,
  ProjectHealth,
  RiskHighlight,
} from "@/lib/types";
import { ProgressCurveChart, curveReadout } from "@/components/charts/ProgressCurveChart";
import { fmtNum, fmtP6Date, fmtPct } from "@/components/reporting/format";
import {
  AnalyticsState,
  BehindPlanLink,
  BehindPlanTable,
  BudgetActualCard,
  CostGauge,
  GroupBarsCard,
  HoursGauge,
  MonthlyCard,
  TimeVsWork,
  type AnalyticsStatus,
} from "@/components/dashboard/AnalyticsWidgets";
import { HelpTip } from "@/components/HelpTip";
import type { HelpKey } from "@/lib/help";
import { CalendarIcon, CheckIcon, ChevronRightIcon, ClockIcon, TrendingUpIcon, UsersIcon } from "@/components/icons";

export type CurveStatus = "idle" | "loading" | "ready" | "locked" | "error";

export interface WidgetContext {
  project: Project;
  summary: DashboardSummary | null;
  health: ProjectHealth | null;
  risks: RiskHighlight[] | null;
  curve: ProgressCurve | null;
  curveStatus: CurveStatus;
  deadlineDays: number | null;
  analytics: ProjectAnalytics | null;
  analyticsStatus: AnalyticsStatus;
}

interface WidgetDef {
  title: string;
  description: string;
  span: "kpi" | "third" | "half" | "full";
  // true → page wraps the body in card padding; false → widget draws edge-to-edge
  // (tables, lists, self-padded blocks).
  pad?: boolean;
  /** Optional right-hand side of the card header (a chip, a link). */
  action?: (ctx: WidgetContext) => ReactNode;
  /** The "?" in the card header (lib/help.ts). */
  help?: HelpKey;
  /** Optional count shown beside the title in the muted weight. */
  count?: (ctx: WidgetContext) => number | null;
  render: (ctx: WidgetContext) => ReactNode;
  /** Leave the widget off the page (it stays in the configure modal). */
  hidden?: (ctx: WidgetContext) => boolean;
}

/** Render an analytics block once the payload is in, a status line until then. */
function withAnalytics(what: string, body: (a: ProjectAnalytics) => ReactNode) {
  return function AnalyticsBlock({ analytics, analyticsStatus }: WidgetContext) {
    return analytics ? body(analytics) : <AnalyticsState status={analyticsStatus} what={what} />;
  };
}

type Tone = "good" | "warn" | "crit" | "info" | "neutral";

// Where each Project Health factor's detail lives. Activity Workspace takes a
// preset filter (see activity-workspace/page.tsx) so the critical-path / overdue rows
// land on the exact activity list behind the number.
const HEALTH_FACTOR_HREF: Record<HealthFactorKey, string> = {
  // Reminding non-responders and closing the period both live on Dashboard itself.
  scope_submissions: "/dashboard",
  evm: "/evm",
  critical_path: "/activity-workspace?filter=critical",
  overdue: "/activity-workspace?filter=overdue",
};

const HEALTH_STATUS_TEXT: Record<HealthStatus, string> = {
  good: "Healthy",
  warn: "Needs attention",
  crit: "At risk",
  unknown: "Not enough data",
};

const RISK_SEVERITY_TEXT: Record<RiskHighlight["severity"], string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const DAY_MS = 86_400_000;

/** Whole calendar days from today to an ISO date; negative once it has passed. */
function daysFromToday(iso: string | null): number | null {
  if (!iso) return null;
  const target = Date.parse(iso.slice(0, 10));
  if (Number.isNaN(target)) return null;
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / DAY_MS);
}

/** Same bands as the report's progress block and the health factors. */
function spiTone(spi: number | null): Tone {
  if (spi == null) return "neutral";
  if (spi >= 0.95) return "good";
  if (spi >= 0.85) return "warn";
  return "crit";
}

function spiNote(spi: number | null): string {
  if (spi == null) return "Not enough data";
  if (spi >= 1.05) return "Ahead of plan";
  if (spi >= 0.95) return "On plan";
  return "Behind plan";
}

/** The latest schedule import stands in for the period cards only while no
 *  subcontractor update period is running — that workflow wins when it is. */
function fallbackUpdate(summary: DashboardSummary | null): CurrentUpdate | null {
  if (!summary || summary.active_period_id) return null;
  return summary.current_update;
}

function Kpi({
  label,
  icon,
  tone,
  title,
  help,
  children,
  footer,
}: {
  label: string;
  icon: ReactNode;
  tone: Tone;
  title?: string;
  help?: HelpKey;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="card kpi" title={title}>
      <div className="kpi-top">
        <span className="kpi-label">
          {label}
          {help && <HelpTip id={help} />}
        </span>
        <div className={`kpi-icon is-${tone}`}>{icon}</div>
      </div>
      {children}
      {footer && <div className="kpi-foot">{footer}</div>}
    </div>
  );
}

function ProgressStats({
  planned,
  actual,
  spi,
}: {
  planned: number | null;
  actual: number | null;
  spi: number | null;
}) {
  if (planned == null && actual == null) return null;
  const gap = planned != null && actual != null ? actual - planned : null;
  const effSpi = spi ?? (planned != null && actual != null && planned > 0 ? actual / planned : null);
  const tone = spiTone(effSpi);
  return (
    <div className="dash-progress-stats">
      <div className="dash-stat">
        <span className="dash-stat-label">
          <i className="dash-swatch is-planned" />
          Planned
        </span>
        <span className="dash-stat-value num">{fmtPct(planned)}</span>
        <span className="dash-stat-note">Baseline, due by the data date</span>
      </div>
      <div className="dash-stat">
        <span className="dash-stat-label">
          <i className="dash-swatch is-actual" />
          Actual
        </span>
        <span className="dash-stat-value num">{fmtPct(actual)}</span>
        <span className="dash-stat-note">Current schedule, earned to date</span>
      </div>
      <div className="dash-stat">
        <span className="dash-stat-label">Gap</span>
        <span className={`dash-stat-value num tone-${tone}`}>
          {gap == null ? "—" : `${gap > 0 ? "+" : ""}${fmtNum(gap, 1)} pts`}
        </span>
        <span className="dash-stat-note">{spiNote(effSpi)}</span>
      </div>
      <div className="dash-stat">
        <span className="dash-stat-label">SPI</span>
        <span className={`dash-stat-value num tone-${tone}`}>{fmtNum(effSpi)}</span>
        <span className="dash-stat-note">Actual ÷ planned</span>
      </div>
    </div>
  );
}

export const WIDGET_REGISTRY: Record<DashboardWidgetKey, WidgetDef> = {
  "update-period": {
    title: "Update Period",
    description: "Current period and its status",
    span: "kpi",
    render: ({ summary }) => {
      const cu = fallbackUpdate(summary);
      if (cu) {
        const hasPrevious = Boolean(cu.previous_label || cu.previous_data_date);
        return (
          <Kpi
            label="Current update"
            help="dash.current-update"
            tone="info"
            icon={<CalendarIcon className="icon" />}
            title={cu.filename}
            footer={
              <>
                <div className="kpi-sub">
                  Data date <span className="num">{fmtP6Date(cu.data_date)}</span>
                </div>
                {hasPrevious && (
                  <div className="kpi-sub kpi-sub-muted">
                    Previous {cu.previous_label ?? "update"} ·{" "}
                    <span className="num">{fmtP6Date(cu.previous_data_date)}</span>
                  </div>
                )}
              </>
            }
          >
            <div className="kpi-value kpi-value-text">{cu.revision_label ?? "Latest import"}</div>
          </Kpi>
        );
      }

      const status = summary?.active_period_status;
      const deadline = summary?.deadline_at;
      const inPeriod = Boolean(summary?.active_period_id);
      return (
        <Kpi
          label="Update period"
          tone={status === "open" ? "good" : "neutral"}
          icon={<CheckIcon className="icon" />}
          footer={
            <div className="kpi-sub">
              {deadline ? (
                <>
                  Deadline <span className="num">{fmtP6Date(deadline)}</span>
                </>
              ) : inPeriod ? (
                "No deadline set"
              ) : (
                "No open period or schedule upload yet"
              )}
            </div>
          }
        >
          <div className="kpi-value kpi-value-text">
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
    render: ({ summary, deadlineDays }) => {
      const cu = fallbackUpdate(summary);
      if (cu) {
        const days = daysFromToday(cu.next_data_date);
        const cadence = cu.cadence_days != null ? Math.round(cu.cadence_days) : null;
        let value: ReactNode;
        let tone: Tone = "info";
        if (days === null) {
          value = "—";
          tone = "neutral";
        } else if (days > 0) {
          value = (
            <>
              {fmtNum(days, 0)}
              <span className="kpi-unit"> {days === 1 ? "day" : "days"}</span>
            </>
          );
        } else if (days === 0) {
          value = "Due";
          tone = "warn";
        } else {
          value = (
            <>
              {fmtNum(-days, 0)}
              <span className="kpi-unit"> {days === -1 ? "day" : "days"} overdue</span>
            </>
          );
          // A week late is a slipping cadence; beyond that the dashboard is stale.
          tone = days >= -7 ? "warn" : "crit";
        }
        return (
          <Kpi
            label="Next update"
            help="dash.next-update"
            tone={tone}
            icon={<ClockIcon className="icon" />}
            footer={
              days === null ? (
                <div className="kpi-sub kpi-sub-muted">Not enough updates to estimate a cycle</div>
              ) : (
                <div className="kpi-sub">
                  Expected <span className="num">{fmtP6Date(cu.next_data_date)}</span>
                  {cadence != null && ` · ${cadence}-day cycle`}
                </div>
              )
            }
          >
            <div className={`kpi-value${tone === "warn" || tone === "crit" ? ` tone-${tone}` : ""}`}>{value}</div>
          </Kpi>
        );
      }

      return (
        <Kpi
          label="Deadline countdown"
          tone="warn"
          icon={<ClockIcon className="icon" />}
          footer={<div className="kpi-sub">Until this period closes</div>}
        >
          <div className="kpi-value">
            {deadlineDays ?? "—"}
            {deadlineDays !== null && <span className="kpi-unit"> {deadlineDays === 1 ? "day" : "days"}</span>}
          </div>
        </Kpi>
      );
    },
  },

  "scopes-submitted": {
    title: "Scopes Submitted",
    description: "Subcontractor submission progress",
    span: "kpi",
    render: ({ summary }) => {
      const cu = fallbackUpdate(summary);
      if (cu) {
        const total = cu.activities_total;
        const done = cu.activities_complete;
        const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;
        const firstUpdate = cu.finished_this_update == null;
        return (
          <Kpi
            label="This update"
            help="dash.this-update"
            tone="good"
            icon={<CheckIcon className="icon" />}
            footer={
              <>
                <div className="progress" aria-hidden="true">
                  <span style={{ width: `${pct}%`, background: "var(--good)" }} />
                </div>
                <div className="kpi-sub">
                  {firstUpdate
                    ? `${fmtPct(pct)} complete · ${fmtNum(cu.activities_in_progress, 0)} in progress`
                    : `${fmtNum(done, 0)} of ${fmtNum(total, 0)} complete · ${fmtNum(cu.activities_in_progress, 0)} in progress`}
                </div>
                {!firstUpdate && (
                  <div className="kpi-sub" title="Completed activities over all activities — a count, not weighted by duration or manhours">
                    <b className="num">{fmtPct(pct)}</b> of activities complete
                  </div>
                )}
              </>
            }
          >
            {firstUpdate ? (
              <div className="kpi-value">
                {fmtNum(done, 0)}
                <span className="kpi-unit"> / {fmtNum(total, 0)}</span>
              </div>
            ) : (
              <div className="kpi-value-row">
                <div className="kpi-value">
                  {fmtNum(cu.finished_this_update, 0)}
                  <span className="kpi-unit"> finished</span>
                </div>
                <span className="kpi-aside">{fmtNum(cu.started_this_update, 0)} started</span>
              </div>
            )}
          </Kpi>
        );
      }

      const total = summary?.orgs_total ?? 0;
      const done = summary?.orgs_submitted ?? 0;
      const pct = total > 0 ? Math.round((done / total) * 100) : 0;
      return (
        <Kpi
          label="Scopes submitted"
          tone="info"
          icon={<UsersIcon className="icon" />}
          footer={
            <div className="progress" aria-hidden="true">
              <span style={{ width: `${pct}%`, background: "var(--info)" }} />
            </div>
          }
        >
          <div className="kpi-value">
            {done}
            <span className="kpi-unit"> / {total}</span>
          </div>
        </Kpi>
      );
    },
  },

  recovery: {
    title: "Recovery Plans",
    description: "Slipped activities that need a recovery plan",
    span: "kpi",
    render: ({ summary }) => {
      const required = summary?.recovery_required ?? 0;
      const done = summary?.recovery_acknowledged ?? 0;
      const open = Math.max(0, required - done);
      return (
        <Kpi
          label="Recovery plans"
          help="dash.recovery"
          tone={open > 0 ? "warn" : "neutral"}
          icon={<TrendingUpIcon className="icon" />}
          footer={
            <div className={`kpi-sub${open > 0 ? "" : " kpi-sub-muted"}`}>
              {required === 0 ? (
                "No slip needs a plan this update"
              ) : (
                <Link href="/recovery-plan">
                  {done} of {required} acknowledged
                </Link>
              )}
            </div>
          }
        >
          <div className="kpi-value">
            {fmtNum(open, 0)}
            <span className="kpi-unit"> open</span>
          </div>
        </Kpi>
      );
    },
  },

  "hours-gauge": {
    help: "dash.hours",
    title: "Labor Hours",
    description: "Actual vs planned units % against the baseline",
    span: "third",
    render: withAnalytics("labor hours", (a) => <HoursGauge a={a} />),
  },

  "cost-gauge": {
    help: "dash.cost",
    title: "Cost",
    description: "Spent vs planned spend against the baseline",
    span: "third",
    // Without cost-loaded resources the card would only ever say so.
    hidden: ({ analytics }) => analytics != null && analytics.cost == null,
    render: withAnalytics("cost", (a) => <CostGauge a={a} />),
  },

  "time-vs-work": {
    help: "dash.time-vs-work",
    title: "Time vs Work",
    description: "Share of the baseline span elapsed vs share of work done",
    span: "third",
    render: withAnalytics("time vs work", (a) => <TimeVsWork a={a} />),
  },

  "monthly-hours": {
    help: "dash.monthly",
    title: "Monthly Progress",
    description: "Planned vs actual by month, with the cumulative curves",
    span: "full",
    render: withAnalytics("monthly progress", (a) => <MonthlyCard a={a} />),
  },

  "hours-by-group": {
    help: "dash.by-group",
    title: "Progress by WBS / Code",
    description: "Planned to date vs actual for each branch or code value",
    span: "half",
    render: withAnalytics("progress by group", (a) => <GroupBarsCard a={a} />),
  },

  "behind-plan": {
    help: "dash.behind-plan",
    title: "Behind Plan",
    description: "Unfinished activities trailing the baseline's planned %",
    span: "half",
    count: ({ analytics }) => (analytics ? analytics.behind_total : null),
    action: () => <BehindPlanLink />,
    render: withAnalytics("behind-plan activities", (a) => <BehindPlanTable a={a} />),
  },

  "budget-actual": {
    help: "dash.budget-actual",
    title: "Budget vs Actual",
    description: "Budget at completion, actual to date and the cumulative trend",
    span: "half",
    render: withAnalytics("budget vs actual", (a) => <BudgetActualCard a={a} />),
  },

  "health-badge": {
    help: "dash.health",
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
            <div className="health-summary">
              <div className="health-score">
                {health.score ?? "—"}
                {health.score !== null && <small> / 100</small>}
              </div>
              <div className={`health-status tone-${s === "unknown" ? "neutral" : s}`}>{HEALTH_STATUS_TEXT[s]}</div>
              {health.score !== null && (
                <div className="progress health-meter" aria-hidden="true">
                  <span
                    style={{
                      width: `${Math.min(Math.max(health.score, 0), 100)}%`,
                      background: s === "unknown" ? "var(--border-strong)" : `var(--${s})`,
                    }}
                  />
                </div>
              )}
            </div>
          </div>
          <div className="health-factors">
            {health.factors.map((f) => (
              <a
                key={f.label}
                className="health-factor"
                href={HEALTH_FACTOR_HREF[f.key]}
                target="_blank"
                rel="noopener noreferrer"
                title="Open details in a new tab"
              >
                <span className={`dot ${f.status}`} aria-hidden="true" />
                <span className="hf-text">
                  <span className="fl">{f.label}</span>
                  <span className="fd">{f.detail}</span>
                </span>
              </a>
            ))}
          </div>
        </div>
      );
    },
  },

  "s-curve": {
    help: "dash.s-curve",
    title: "Progress Curve",
    description: "Planned vs actual % complete against the baseline",
    span: "full",
    action: ({ curve }) =>
      curve ? (
        <span className="chip chip-neutral">
          {/* A label like "Baseline" or "Baseline v2" already says what it is. */}
          {/^baseline\b/i.test(curve.version_label) ? curve.version_label : `Baseline ${curve.version_label}`}
        </span>
      ) : null,
    render: ({ curve, curveStatus, project, summary }) => {
      const cu = summary?.current_update ?? null;
      const readout = curve ? curveReadout(curve.points, curve.data_date) : null;
      const planned = cu?.planned_pct ?? readout?.planned ?? null;
      const actual = cu?.actual_pct ?? readout?.actual ?? null;

      let body: ReactNode;
      if (curveStatus === "locked") {
        body = (
          <p className="empty-state">
            Lock a baseline for <b>{project.name}</b> to see the progress curve.
          </p>
        );
      } else if (curveStatus === "loading" || curveStatus === "idle") {
        body = <p className="empty-state">Loading the progress curve…</p>;
      } else if (!curve) {
        body = <p className="empty-state">Progress curve unavailable.</p>;
      } else if (curve.points.length < 2) {
        body = (
          <p className="empty-state">
            Not enough dated points yet — the curve fills in as schedule updates are uploaded.
          </p>
        );
      } else {
        body = <ProgressCurveChart points={curve.points} dataDate={curve.data_date} />;
      }

      return (
        <div className="dash-progress">
          <ProgressStats planned={planned} actual={actual} spi={cu?.spi ?? null} />
          {body}
        </div>
      );
    },
  },

  "risk-top3": {
    help: "dash.risks",
    title: "Top Risks",
    description: "Highest-signal schedule and delivery risks",
    span: "half",
    count: ({ risks }) => (risks ? risks.length : null),
    action: () => (
      <Link href="/risk/register" className="card-link">
        Risk register
        <ChevronRightIcon className="icon" aria-hidden="true" />
      </Link>
    ),
    render: ({ risks }) => {
      if (!risks) return <p className="empty-state">Risk highlights unavailable.</p>;
      if (risks.length === 0) return <p className="empty-state">No standout risks right now.</p>;
      return (
        <div className="risk-list">
          {risks.map((r, i) => (
            <div key={`${r.title}-${i}`} className="risk-item">
              <span className={`risk-sev ${r.severity}`} aria-hidden="true" />
              <div className="risk-body">
                <div className="risk-title">{r.title}</div>
                <div className="risk-detail">{r.detail}</div>
                <div className="risk-meta">
                  <span className={`risk-sev-label ${r.severity}`}>{RISK_SEVERITY_TEXT[r.severity]}</span>
                  <span>{r.source}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      );
    },
  },

  "scope-table": {
    help: "dash.scopes",
    title: "Scope Submission Status",
    description: "Per-subcontractor submission and progress",
    span: "full",
    count: ({ summary }) => (summary ? summary.scope_status.length : null),
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
                  <td className="num">{fmtNum(row.activity_count, 0)}</td>
                  <td className="num">{fmtPct(row.avg_percent_complete)}</td>
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

// Recommended order — also what an unsaved (default) layout is shown in: the
// KPI row, the three gauges, the progress curve and monthly bars full width,
// then the half-width pairs (by group | behind plan, budget | health).
export const WIDGET_ORDER: DashboardWidgetKey[] = [
  "update-period",
  "deadline",
  "scopes-submitted",
  "recovery",
  "hours-gauge",
  "cost-gauge",
  "time-vs-work",
  "s-curve",
  "monthly-hours",
  "hours-by-group",
  "behind-plan",
  "budget-actual",
  "health-badge",
  "risk-top3",
  "scope-table",
];
