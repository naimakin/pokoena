"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { api } from "@/lib/api";
import { ScurveChart } from "@/components/ScurveChart";
import { FloatBadge, fmtDays, fmtNum, fmtP6Date, fmtPct } from "@/components/reporting/format";
import type {
  Activity,
  BaselineVariance,
  DcmaReport,
  EvmScurve,
  EvmSummary,
  FloatPathEndCandidate,
  FloatPathReport,
  MonteCarloResult,
  Project,
  ProjectStatus,
  ReportHeader,
  RiskItem,
  ScheduleChangeReport,
} from "@/lib/types";

// One registry entry per key in the server-side catalogue
// (backend/app/api/routes/reports.py::BLOCK_CATALOGUE). The two must stay in
// sync — a key the server knows and this file doesn't renders as nothing.

export interface BlockContext {
  project: Project;
  header: ReportHeader | null;
  narrative: string | null;
  options: Record<string, unknown>;
}

function num(options: Record<string, unknown>, key: string, fallback: number): number {
  const value = options[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function str(options: Record<string, unknown>, key: string, fallback: string): string {
  const value = options[key];
  return typeof value === "string" && value ? value : fallback;
}

/** Every block is "fetch one thing, then draw it". This keeps the loading and
 *  empty states identical across all of them, which matters more in a printed
 *  report than on a screen: a half-rendered block must never look like a real
 *  answer of zero. */
function useBlockData<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "empty">("loading");

  useEffect(() => {
    let live = true;
    setState("loading");
    load()
      .then((result) => {
        if (!live) return;
        setData(result);
        setState("ready");
      })
      .catch(() => {
        if (!live) return;
        setData(null);
        setState("empty");
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, state };
}

function BlockShell({
  title,
  subtitle,
  state,
  unavailable,
  children,
}: {
  title: string;
  subtitle?: string;
  state: "loading" | "ready" | "empty";
  unavailable: string;
  children: ReactNode;
}) {
  return (
    <section className="card report-block">
      <div className="card-head">
        <div>
          <div className="card-title">{title}</div>
          {subtitle && <div className="card-title-sub">{subtitle}</div>}
        </div>
      </div>
      {state === "loading" && <p className="empty-state">Loading…</p>}
      {state === "empty" && <p className="empty-state">{unavailable}</p>}
      {state === "ready" && children}
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="report-metric">
      <div className="report-metric-label">{label}</div>
      <div className="report-metric-value">{value}</div>
      {note && <div className="report-metric-note">{note}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Blocks
// ---------------------------------------------------------------------------

function CoverBlock({ project, header }: BlockContext) {
  return (
    <section className="card report-block report-cover">
      <div className="report-cover-body">
        <div className="report-cover-kicker">{header?.project_code ?? project.code}</div>
        <h1 className="report-cover-title">{project.name}</h1>
        <dl className="report-cover-facts">
          <div>
            <dt>Data date</dt>
            <dd className="mono">{fmtP6Date(header?.data_date)}</dd>
          </div>
          <div>
            <dt>Schedule revision</dt>
            <dd className="mono">{header?.schedule_revision ?? "—"}</dd>
          </div>
          <div>
            <dt>Source file</dt>
            <dd className="mono">{header?.schedule_filename ?? "—"}</dd>
          </div>
          <div>
            <dt>Baseline</dt>
            <dd className="mono">{header?.baseline_label ?? "None locked"}</dd>
          </div>
          <div>
            <dt>Issued</dt>
            <dd className="mono">{fmtP6Date(header?.generated_at)}</dd>
          </div>
          <div>
            <dt>Prepared by</dt>
            <dd>{header?.generated_by ?? "—"}</dd>
          </div>
        </dl>
        <div className="report-cover-basis">
          Progress basis: {header?.progress_basis ?? "—"}
        </div>
        {header?.baseline_changed_since && (
          <div className="banner warn">
            <span className="banner-text">
              The baseline was re-locked after this programme was imported. State why in the executive
              summary — a changed baseline with no explanation is the most common reason a report is
              rejected.
            </span>
          </div>
        )}
        <div className="report-signoff">
          <div>
            <span>Prepared by</span>
          </div>
          <div>
            <span>Checked by</span>
          </div>
          <div>
            <span>Approved by</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function ExecutiveSummaryBlock({ project, narrative }: BlockContext) {
  const { data, state } = useBlockData<ProjectStatus>(
    () => api.get<ProjectStatus>(`/projects/${project.id}/status`),
    [project.id],
  );

  return (
    <BlockShell
      title="Executive summary"
      state={state === "loading" ? "loading" : "ready"}
      unavailable=""
    >
      <div className="report-body">
        {narrative ? (
          narrative.split(/\n{2,}/).map((para, i) => <p key={i}>{para}</p>)
        ) : (
          <p className="empty-state" style={{ textAlign: "left", padding: 0 }}>
            No narrative written yet. Add one on the report format — the computed verdicts below are
            the starting point, not the report.
          </p>
        )}
        {data && state === "ready" && (
          <div className="report-metrics">
            <Metric label="Progress" value={data.summary.progress.verdict} note={data.summary.progress.headline} />
            <Metric label="Risk" value={data.summary.risk.verdict} note={data.summary.risk.headline} />
            <Metric label="Quality" value={data.summary.quality.verdict} note={data.summary.quality.headline} />
          </div>
        )}
      </div>
    </BlockShell>
  );
}

const MILESTONE_TYPES = new Set(["TT_Mile", "TT_FinMile"]);

function MilestonesBlock({ project }: BlockContext) {
  const { data, state } = useBlockData(
    async () => {
      const [activities, variance] = await Promise.all([
        api.get<Activity[]>(`/activities?project_id=${project.id}`),
        api
          .get<BaselineVariance>(`/projects/${project.id}/evm/baseline/variance`)
          .catch(() => null),
      ]);
      const baselineByExternalId = new Map(
        (variance?.rows ?? []).map((r) => [r.external_id, r]),
      );
      const rows = activities
        .filter((a) => MILESTONE_TYPES.has(a.task_type ?? ""))
        .map((a) => ({ activity: a, baseline: baselineByExternalId.get(a.external_id) ?? null }))
        .sort((x, y) =>
          (x.activity.early_finish ?? x.activity.planned_finish ?? "9999").localeCompare(
            y.activity.early_finish ?? y.activity.planned_finish ?? "9999",
          ),
        );
      if (rows.length === 0) throw new Error("no milestones");
      return rows;
    },
    [project.id],
  );

  return (
    <BlockShell
      title="Key dates and milestones"
      subtitle="Forecast against baseline, with variance in days"
      state={state}
      unavailable="No milestone activities in the current programme."
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Milestone</th>
              <th>Baseline</th>
              <th>Forecast</th>
              <th>Variance</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map(({ activity, baseline }) => {
              const variance = baseline?.finish_variance_days ?? null;
              return (
                <tr key={activity.external_id} className={activity.is_critical ? "critical" : undefined}>
                  <td>
                    <div className="subname">{activity.name}</div>
                    <div className="actid">{activity.external_id}</div>
                  </td>
                  <td className="num">{fmtP6Date(baseline?.baseline_finish)}</td>
                  <td className="num">
                    {fmtP6Date(activity.actual_finish ?? activity.early_finish ?? activity.planned_finish)}
                  </td>
                  <td className="num">
                    {variance == null ? (
                      "—"
                    ) : (
                      <span className={variance > 0 ? "float-badge float-zero" : "float-badge float-high"}>
                        {fmtDays(variance)}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`chip ${activity.actual_finish ? "chip-good" : "chip-neutral"}`}>
                      {activity.actual_finish ? "Achieved" : "Forecast"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </BlockShell>
  );
}

function ProgressVsPlanBlock({ project }: BlockContext) {
  const { data, state } = useBlockData(
    async () => {
      const summary = await api.get<EvmSummary>(`/projects/${project.id}/evm/summary`);
      if (!summary.baseline_id) throw new Error("no baseline");
      return summary;
    },
    [project.id],
  );

  return (
    <BlockShell
      title="Progress: planned vs actual"
      subtitle={data ? `Against baseline ${data.version_label}` : undefined}
      state={state}
      unavailable="Lock a baseline in Planning > Baselines — planned progress has nothing to measure against until then."
    >
      {data && (
        <div className="report-metrics" style={{ padding: "1rem 1.1rem" }}>
          <Metric label="Planned complete" value={fmtPct(data.pct_planned)} />
          <Metric label="Earned complete" value={fmtPct(data.pct_earned)} />
          <Metric
            label="SPI"
            value={fmtNum(data.spi)}
            note={data.spi != null && data.spi < 1 ? "Behind schedule" : "At or ahead of plan"}
          />
          <Metric
            label="CPI"
            value={fmtNum(data.cpi)}
            note={data.cpi != null && data.cpi < 1 ? "Over spent" : "At or under budget"}
          />
          <Metric label="Schedule variance" value={`${fmtNum(data.sv, 0)} h`} />
          <Metric label="Cost variance" value={`${fmtNum(data.cv, 0)} h`} />
          <Metric label="BAC" value={`${fmtNum(data.bac, 0)} h`} />
          <Metric label="EAC" value={`${fmtNum(data.eac, 0)} h`} />
        </div>
      )}
    </BlockShell>
  );
}

function ScurveBlock({ project, options }: BlockContext) {
  const granularity = str(options, "granularity", "monthly");
  const { data, state } = useBlockData<EvmScurve>(
    () => api.get<EvmScurve>(`/projects/${project.id}/evm/scurve?granularity=${granularity}`),
    [project.id, granularity],
  );

  return (
    <BlockShell
      title="S-curve"
      subtitle={`Cumulative planned value, earned value and actual cost — ${granularity}`}
      state={state}
      unavailable="Lock a baseline in Planning > Baselines to generate the planned-value curve."
    >
      {data && <ScurveChart series={data.series} />}
    </BlockShell>
  );
}

function WbsProgressBlock({ project }: BlockContext) {
  const { data, state } = useBlockData(
    async () => {
      const activities = await api.get<Activity[]>(`/activities?project_id=${project.id}`);
      const byBranch = new Map<string, { count: number; weighted: number; hours: number }>();
      for (const a of activities) {
        if ((a.task_type ?? "") === "TT_WBS") continue;
        const branch = (a.wbs_path ?? "Unassigned").split(" > ")[0] || "Unassigned";
        const row = byBranch.get(branch) ?? { count: 0, weighted: 0, hours: 0 };
        const hours = a.target_duration_hours ?? 0;
        row.count += 1;
        row.hours += hours;
        row.weighted += (a.percent_complete / 100) * hours;
        byBranch.set(branch, row);
      }
      const rows = [...byBranch].map(([branch, r]) => ({
        branch,
        count: r.count,
        hours: r.hours,
        pct: r.hours > 0 ? (r.weighted / r.hours) * 100 : 0,
      }));
      if (rows.length === 0) throw new Error("no activities");
      return rows.sort((a, b) => b.hours - a.hours);
    },
    [project.id],
  );

  return (
    <BlockShell
      title="Progress by WBS"
      subtitle="Percent complete weighted by original duration"
      state={state}
      unavailable="No activities in the current programme."
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>WBS branch</th>
              <th>Activities</th>
              <th>Budget (h)</th>
              <th>Complete</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((r) => (
              <tr key={r.branch}>
                <td>{r.branch}</td>
                <td className="num">{r.count}</td>
                <td className="num">{fmtNum(r.hours, 0)}</td>
                <td className="num">
                  <div className="report-bar">
                    <div className="report-bar-fill" style={{ width: `${Math.min(r.pct, 100)}%` }} />
                    <span>{fmtPct(r.pct)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BlockShell>
  );
}

function CriticalPathBlock({ project, options }: BlockContext) {
  const limit = num(options, "limit", 30);
  const { data, state } = useBlockData(
    async () => {
      const activities = await api.get<Activity[]>(`/activities?project_id=${project.id}`);
      const rows = activities
        .filter((a) => (a.is_longest_path || a.is_critical) && (a.task_type ?? "") !== "TT_WBS")
        .filter((a) => a.status !== "complete")
        .sort((x, y) => (x.early_start ?? "9999").localeCompare(y.early_start ?? "9999"))
        .slice(0, limit);
      if (rows.length === 0) throw new Error("no critical activities");
      return rows;
    },
    [project.id, limit],
  );

  return (
    <BlockShell
      title="Critical path"
      subtitle="Incomplete activities on the longest path or at zero float, in date order"
      state={state}
      unavailable="No incomplete critical activities — either the programme has no CPM results yet or the critical work is done."
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Activity</th>
              <th>Remaining</th>
              <th>Early start</th>
              <th>Early finish</th>
              <th>Total float</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((a) => (
              <tr key={a.external_id} className="critical">
                <td>
                  <div className="subname">{a.name}</div>
                  <div className="actid">
                    {a.external_id}
                    {a.wbs_path ? ` · ${a.wbs_path}` : ""}
                  </div>
                </td>
                <td className="num">{fmtNum((a.remaining_duration_hours ?? 0) / 8, 1)}d</td>
                <td className="num">{fmtP6Date(a.early_start)}</td>
                <td className="num">{fmtP6Date(a.early_finish)}</td>
                <td className="num">
                  <FloatBadge days={a.total_float_hours != null ? a.total_float_hours / 8 : null} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BlockShell>
  );
}

function FloatPathsBlock({ project, options }: BlockContext) {
  const pathCount = num(options, "path_count", 3);
  const { data, state } = useBlockData<FloatPathReport>(
    async () => {
      const candidates = await api.get<FloatPathEndCandidate[]>(
        `/projects/${project.id}/float-path/end-candidates`,
      );
      const milestones = candidates.filter((c) => MILESTONE_TYPES.has(c.task_type ?? ""));
      const end = milestones[milestones.length - 1] ?? candidates[candidates.length - 1];
      if (!end) throw new Error("no activities");
      return api.get<FloatPathReport>(
        `/projects/${project.id}/float-path?end_activity=${encodeURIComponent(end.external_id)}&path_count=${pathCount}`,
      );
    },
    [project.id, pathCount],
  );

  return (
    <BlockShell
      title="Float paths"
      subtitle={
        data
          ? `Driving chains into ${data.end_activity_external_id} — ${data.end_activity_name ?? ""}`
          : undefined
      }
      state={state}
      unavailable="No schedule logic to walk — import a programme with relationships first."
    >
      {data && (
        <>
          {data.acceleration_headroom_days != null && (
            <p className="report-note">
              Acceleration headroom is {fmtDays(data.acceleration_headroom_days)}: pulling path 1 in
              further than that makes path 2 critical instead.
            </p>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Path</th>
                  <th>Total float</th>
                  <th>Activities</th>
                  <th>Joins at</th>
                  <th>First activity</th>
                  <th>Last activity</th>
                </tr>
              </thead>
              <tbody>
                {data.paths.map((p) => (
                  <tr key={p.path_no} className={p.path_no === 1 ? "critical" : undefined}>
                    <td className="num">{p.path_no}</td>
                    <td className="num">
                      <FloatBadge days={p.total_float_days} />
                    </td>
                    <td className="num">{p.activities.length}</td>
                    <td className="mono">{p.joins_at_external_id ?? data.end_activity_external_id}</td>
                    <td className="mono">{p.activities[0]?.external_id ?? "—"}</td>
                    <td className="mono">{p.activities[p.activities.length - 1]?.external_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </BlockShell>
  );
}

function BaselineVarianceBlock({ project, options }: BlockContext) {
  const limit = num(options, "limit", 25);
  const { data, state } = useBlockData<BaselineVariance>(
    () => api.get<BaselineVariance>(`/projects/${project.id}/evm/baseline/variance`),
    [project.id],
  );

  const rows = (data?.rows ?? [])
    .filter((r) => (r.finish_variance_days ?? 0) !== 0)
    .sort((a, b) => (b.finish_variance_days ?? 0) - (a.finish_variance_days ?? 0))
    .slice(0, limit);

  return (
    <BlockShell
      title="Baseline variance"
      subtitle={data ? `Against baseline ${data.version_label}, worst slip first` : undefined}
      state={state}
      unavailable="Lock a baseline in Planning > Baselines to compare dates against it."
    >
      {data && (
        <>
          <div className="report-metrics" style={{ padding: "1rem 1.1rem 0" }}>
            <Metric label="Behind" value={String(data.summary.behind)} note="activities" />
            <Metric label="On track" value={String(data.summary.on_track)} note="activities" />
            <Metric label="Ahead" value={String(data.summary.ahead)} note="activities" />
            <Metric
              label="Project finish"
              value={fmtDays(data.summary.project_finish_variance_days)}
              note={fmtP6Date(data.summary.forecast_finish)}
            />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Activity</th>
                  <th>Baseline finish</th>
                  <th>Forecast finish</th>
                  <th>Variance</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="empty-state">
                      No activity has moved off its baseline finish date.
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => (
                    <tr key={r.external_id} className={r.is_critical ? "critical" : undefined}>
                      <td>
                        <div className="subname">{r.name}</div>
                        <div className="actid">
                          {r.external_id}
                          {r.wbs_code ? ` · ${r.wbs_code}` : ""}
                        </div>
                      </td>
                      <td className="num">{fmtP6Date(r.baseline_finish)}</td>
                      <td className="num">{fmtP6Date(r.current_finish)}</td>
                      <td className="num">
                        <span
                          className={
                            (r.finish_variance_days ?? 0) > 0
                              ? "float-badge float-zero"
                              : "float-badge float-high"
                          }
                        >
                          {fmtDays(r.finish_variance_days)}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </BlockShell>
  );
}

function ScheduleChangesBlock({ project }: BlockContext) {
  const { data, state } = useBlockData<ScheduleChangeReport>(
    async () => {
      const report = await api.get<ScheduleChangeReport>(`/projects/${project.id}/schedule-changes`);
      if (report.comparison_basis === "none") throw new Error("nothing to compare");
      return report;
    },
    [project.id],
  );

  return (
    <BlockShell
      title="Schedule changes"
      subtitle={
        data
          ? `${data.from_import?.revision_label ?? "previous"} → ${data.to_import?.revision_label ?? "current"}`
          : undefined
      }
      state={state}
      unavailable="Needs two schedule updates to compare — upload the next .xer from Program Library."
    >
      {data && (
        <div className="report-metrics" style={{ padding: "1rem 1.1rem" }}>
          <Metric label="Added" value={String(data.summary.activities_added)} note="activities" />
          <Metric label="Removed" value={String(data.summary.activities_removed)} note="activities" />
          <Metric label="Modified" value={String(data.summary.activities_modified)} note="activities" />
          <Metric label="Activity IDs changed" value={String(data.summary.activities_renamed)} />
          <Metric
            label="Logic changed"
            value={String(
              data.summary.relationships_added +
                data.summary.relationships_removed +
                data.summary.relationships_modified,
            )}
            note={`${data.summary.relationships_added} added, ${data.summary.relationships_removed} removed, ${data.summary.relationships_modified} retyped`}
          />
          <Metric label="Criticality changed" value={String(data.summary.criticality_changes)} />
        </div>
      )}
    </BlockShell>
  );
}

function LookaheadBlock({ project, header, options }: BlockContext) {
  const weeks = num(options, "weeks", 3);
  const { data, state } = useBlockData(
    async () => {
      const activities = await api.get<Activity[]>(`/activities?project_id=${project.id}`);
      const from = header?.data_date ? new Date(header.data_date) : new Date();
      const to = new Date(from);
      to.setDate(to.getDate() + weeks * 7);
      const inWindow = (iso: string | null | undefined) => {
        if (!iso) return false;
        const d = new Date(iso);
        return d >= from && d <= to;
      };
      const rows = activities
        .filter((a) => (a.task_type ?? "") !== "TT_WBS" && a.status !== "complete")
        .filter((a) => inWindow(a.early_start ?? a.planned_start) || inWindow(a.early_finish ?? a.planned_finish))
        .sort((x, y) =>
          (x.early_start ?? x.planned_start ?? "9999").localeCompare(y.early_start ?? y.planned_start ?? "9999"),
        );
      if (rows.length === 0) throw new Error("nothing in window");
      return rows;
    },
    [project.id, weeks, header?.data_date],
  );

  return (
    <BlockShell
      title={`${weeks}-week lookahead`}
      subtitle={`Activities starting or finishing within ${weeks} weeks of the data date`}
      state={state}
      unavailable={`Nothing starts or finishes in the next ${weeks} weeks.`}
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Activity</th>
              <th>Start</th>
              <th>Finish</th>
              <th>Complete</th>
              <th>Total float</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((a) => (
              <tr key={a.external_id} className={a.is_critical ? "critical" : undefined}>
                <td>
                  <div className="subname">{a.name}</div>
                  <div className="actid">
                    {a.external_id}
                    {a.wbs_path ? ` · ${a.wbs_path}` : ""}
                  </div>
                </td>
                <td className="num">{fmtP6Date(a.early_start ?? a.planned_start)}</td>
                <td className="num">{fmtP6Date(a.early_finish ?? a.planned_finish)}</td>
                <td className="num">{a.percent_complete}%</td>
                <td className="num">
                  <FloatBadge days={a.total_float_hours != null ? a.total_float_hours / 8 : null} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BlockShell>
  );
}

function RiskTopBlock({ project, options }: BlockContext) {
  const count = num(options, "count", 5);
  const { data, state } = useBlockData(
    async () => {
      const risks = await api.get<RiskItem[]>(`/projects/${project.id}/risks`);
      const rows = risks
        .filter((r) => r.status !== "closed")
        .sort((a, b) => b.score - a.score)
        .slice(0, count);
      if (rows.length === 0) throw new Error("no open risks");
      return rows;
    },
    [project.id, count],
  );

  return (
    <BlockShell
      title={`Top ${count} risks`}
      subtitle="Open risks by score, with owner and mitigation status"
      state={state}
      unavailable="No open risks on the register."
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Risk</th>
              <th>Score</th>
              <th>Owner</th>
              <th>Mitigation</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((r) => (
              <tr key={r.id}>
                <td>
                  <div className="subname">{r.title}</div>
                  <div className="actid">
                    {r.code}
                    {r.category ? ` · ${r.category}` : ""}
                  </div>
                </td>
                <td className="num">
                  <span className={`chip ${r.score >= 15 ? "chip-crit" : r.score >= 8 ? "chip-warn" : "chip-neutral"}`}>
                    {r.score}
                  </span>
                </td>
                <td>{r.owner_name ?? "—"}</td>
                <td>
                  <span className="chip chip-neutral">{r.mitigation_status.replace(/_/g, " ")}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BlockShell>
  );
}

function MonteCarloBlock({ project }: BlockContext) {
  const { data, state } = useBlockData<MonteCarloResult>(
    () => api.post<MonteCarloResult>(`/projects/${project.id}/risk/monte-carlo`, {}),
    [project.id],
  );

  return (
    <BlockShell
      title="Probabilistic finish"
      subtitle="Monte Carlo over the current logic, triangular duration sampling"
      state={state}
      unavailable="Needs a schedule with logic and durations to simulate."
    >
      {data && (
        <>
          <div className="report-metrics" style={{ padding: "1rem 1.1rem" }}>
            <Metric label="P10" value={fmtP6Date(data.project_finish_p10)} />
            <Metric label="P50" value={fmtP6Date(data.project_finish_p50)} />
            <Metric label="P80" value={fmtP6Date(data.project_finish_p80)} />
            <Metric label="P90" value={fmtP6Date(data.project_finish_p90)} />
          </div>
          <p className="report-note">
            {data.iterations.toLocaleString()} iterations. The simulation&rsquo;s forward pass does not
            apply calendars, so these dates are indicative of spread rather than exact working dates.
          </p>
        </>
      )}
    </BlockShell>
  );
}

function DcmaBlock({ project }: BlockContext) {
  const { data, state } = useBlockData<DcmaReport>(
    () => api.get<DcmaReport>(`/projects/${project.id}/dcma`),
    [project.id],
  );

  return (
    <BlockShell
      title="DCMA 14-point check"
      subtitle={data ? `Score ${fmtNum(data.overall_score, 0)} / 100 over ${data.in_scope} activities` : undefined}
      state={state}
      unavailable="Import a schedule to run the quality checks."
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Check</th>
              <th>Result</th>
              <th>Threshold</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(data?.checks ?? []).map((c) => (
              <tr key={c.id}>
                <td className="num">{c.id}</td>
                <td>{c.name}</td>
                <td className="num">
                  {c.pct}
                  {c.unit === "%" ? "%" : ` ${c.unit}`}
                </td>
                <td className="num">
                  {c.threshold}
                  {c.unit === "%" ? "%" : ` ${c.unit}`}
                </td>
                <td>
                  <span
                    className={`chip ${
                      c.status === "pass"
                        ? "chip-good"
                        : c.status === "warn"
                          ? "chip-warn"
                          : c.status === "fail"
                            ? "chip-crit"
                            : "chip-neutral"
                    }`}
                  >
                    {c.status === "not_tracked" ? "not tracked" : c.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BlockShell>
  );
}

export const BLOCK_REGISTRY: Record<string, ComponentType<BlockContext>> = {
  cover: CoverBlock,
  "executive-summary": ExecutiveSummaryBlock,
  milestones: MilestonesBlock,
  "progress-vs-plan": ProgressVsPlanBlock,
  "s-curve": ScurveBlock,
  "wbs-progress": WbsProgressBlock,
  "critical-path": CriticalPathBlock,
  "float-paths": FloatPathsBlock,
  "baseline-variance": BaselineVarianceBlock,
  "schedule-changes": ScheduleChangesBlock,
  lookahead: LookaheadBlock,
  "risk-top": RiskTopBlock,
  "monte-carlo": MonteCarloBlock,
  dcma: DcmaBlock,
};
