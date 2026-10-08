"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { api } from "@/lib/api";
import { toDays } from "@/lib/duration";
import { ScurveChart } from "@/components/ScurveChart";
import { FloatBadge, fmtDays, fmtNum, fmtP6Date, fmtPct } from "@/components/reporting/format";
import { FoldCard } from "@/components/reporting/collapse";
import type {
  Activity,
  BaselineVariance,
  DcmaReport,
  EvmScurve,
  FloatPathEndCandidate,
  FloatPathReport,
  MonteCarloResult,
  ProgressSummary,
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

/** Every block except the cover folds (components/reporting/collapse.tsx).
 *  `meta` sits on the right of the header at all times; `hint` only while the
 *  block is folded, to say what is hidden. */
function BlockShell({
  title,
  subtitle,
  meta,
  hint,
  state,
  unavailable,
  children,
}: {
  title: string;
  subtitle?: string;
  meta?: ReactNode;
  hint?: string;
  state: "loading" | "ready" | "empty";
  unavailable: string;
  children: ReactNode;
}) {
  return (
    <FoldCard
      className="report-block"
      title={title}
      subtitle={subtitle}
      meta={state === "ready" ? meta : undefined}
      hint={state === "ready" ? hint : undefined}
    >
      {state === "loading" && <p className="empty-state">Loading…</p>}
      {state === "empty" && <p className="empty-state">{unavailable}</p>}
      {state === "ready" && children}
    </FoldCard>
  );
}

/** Blocks narrow enough to sit two abreast on a wide screen (and on a
 *  landscape sheet). The report page pairs two of these only when they are
 *  adjacent in the format's order, so pairing never reorders a report. */
export const HALF_WIDTH_BLOCKS: ReadonlySet<string> = new Set([
  "wbs-progress",
  "schedule-changes",
  "risk-top",
  "monte-carlo",
]);

type Tone = "good" | "warn" | "crit" | "neutral";

/** KPI tile — the same tile language as the progress block's (.pvp-kpi). Text
 *  values (verdicts) drop the mono face. */
function Metric({
  label,
  value,
  note,
  tone = "neutral",
  text = false,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: Tone;
  text?: boolean;
}) {
  return (
    <div className="report-kpi">
      <div className="report-kpi-label">{label}</div>
      <div className={`report-kpi-value tone-${tone}${text ? "" : " num"}`}>{value}</div>
      {note && <div className="report-kpi-note">{note}</div>}
    </div>
  );
}

/** "24 activities" — the folded-header hint on the long-table blocks. */
function countLabel(count: number | undefined, noun: string): string | undefined {
  if (count == null) return undefined;
  const plural = noun.endsWith("y")
    ? `${noun.slice(0, -1)}ies`
    : /(ch|sh|s|x)$/.test(noun)
      ? `${noun}es`
      : `${noun}s`;
  return `${count} ${count === 1 ? noun : plural}`;
}

/** Forecast-slip tone, same bands as the progress block's finish-delay tile. */
function slipTone(days: number | null | undefined): Tone {
  if (days == null) return "neutral";
  if (days > 30) return "crit";
  if (days > 0) return "warn";
  return "good";
}

type Fill = "good" | "warn" | "crit" | "info" | "neutral";

/** One 100% bar split into counts (behind / on track / ahead, pass / warn /
 *  fail), with a legend that always carries the numbers — the bar is the
 *  shape, the legend is the answer. Segments are separated by a 2px surface
 *  gap rather than outlines. */
function DistributionStrip({
  label,
  unit,
  segments,
}: {
  label: string;
  unit: string;
  segments: { label: string; value: number; fill: Fill }[];
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const share = (value: number) => (total > 0 ? (value / total) * 100 : 0);

  return (
    <div className="report-dist">
      <div
        className="report-dist-bar"
        role="img"
        aria-label={`${label}: ${segments.map((s) => `${s.label} ${s.value}`).join(", ")} ${unit}`}
      >
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <span
              key={s.label}
              className={`report-dist-seg report-fill-${s.fill}`}
              style={{ flexGrow: s.value }}
              title={`${s.label}: ${s.value} ${unit} (${fmtPct(share(s.value))})`}
            />
          ))}
      </div>
      <ul className="report-legend">
        {segments.map((s) => (
          <li key={s.label}>
            <span className={`report-swatch report-fill-${s.fill}`} aria-hidden="true" />
            <span>{s.label}</span>
            <b className="num">{s.value}</b>
            <span className="report-legend-share num">{fmtPct(share(s.value))}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Horizontal bars on one shared scale, value at the tip. For counts that
 *  answer "how much of each" rather than "what share of the whole". */
function BarList({ rows }: { rows: { label: string; value: number; note?: string }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="report-hbars">
      {rows.map((r) => (
        <li key={r.label} className="report-hbar">
          <span className="report-hbar-label">
            {r.label}
            {r.note && <span className="report-hbar-note">{r.note}</span>}
          </span>
          <span className="report-hbar-track" aria-hidden="true">
            {r.value > 0 && (
              <span className="report-hbar-fill report-fill-info" style={{ width: `${(r.value / max) * 100}%` }} />
            )}
          </span>
          <span className="report-hbar-value num">{fmtNum(r.value, 0)}</span>
        </li>
      ))}
    </ul>
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
      </div>
      {data && state === "ready" && (
        <div className="report-kpis report-kpis-3">
          {(["progress", "risk", "quality"] as const).map((kind) => (
            <Metric
              key={kind}
              label={kind === "progress" ? "Progress" : kind === "risk" ? "Risk" : "Quality"}
              value={sentenceCase(data.summary[kind].verdict)}
              note={data.summary[kind].headline}
              tone={verdictTone(kind, data.summary[kind].verdict)}
              text
            />
          ))}
        </div>
      )}
    </BlockShell>
  );
}

/** The status rollup's verdicts arrive in capitals ("BEHIND SCHEDULE"); the
 *  report shows them in sentence case like every other label. */
function sentenceCase(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1).toLowerCase() : "—";
}

/** Same mapping as Reports > Project Status (toneFor): Low/Medium/High mean
 *  opposite things for risk and for quality. */
function verdictTone(kind: "progress" | "risk" | "quality", verdict: string): Tone {
  if (kind === "quality") return verdict === "HIGH" ? "good" : verdict === "MEDIUM" ? "warn" : "crit";
  if (kind === "risk") return verdict === "HIGH" ? "crit" : verdict === "MEDIUM" ? "warn" : "good";
  if (verdict === "AHEAD" || verdict === "ON TRACK") return "good";
  if (verdict === "BEHIND SCHEDULE") return "crit";
  return "neutral";
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
      hint={countLabel(data?.length, "milestone")}
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

/** Same bands as the dashboard's health factors (api/routes/dashboard.py::_index_status). */
function spiTone(spi: number | null | undefined): Tone {
  if (spi == null) return "neutral";
  if (spi >= 0.95) return "good";
  if (spi >= 0.85) return "warn";
  return "crit";
}

function spiNote(spi: number | null | undefined): string {
  if (spi == null) return "Not enough data";
  if (spi >= 1.05) return "Ahead of plan";
  if (spi >= 0.95) return "On plan";
  return "Behind plan";
}

function daysBetween(fromIso: string | null, toIso: string | null): number | null {
  if (!fromIso || !toIso) return null;
  return Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 86_400_000);
}

/** Calendar months, one decimal — "15.8 months". */
function fmtMonths(days: number | null): string {
  if (days == null) return "—";
  const months = Math.round((days / 30.44) * 10) / 10;
  return `${months} ${Math.abs(months) === 1 ? "month" : "months"}`;
}

function ProgressVsPlanBlock({ project }: BlockContext) {
  const { data, state } = useBlockData<ProgressSummary>(
    () => api.get<ProgressSummary>(`/projects/${project.id}/evm/progress-summary`),
    [project.id],
  );

  const planned = data?.planned_pct ?? null;
  const actual = data?.actual_pct ?? null;
  const gap = planned != null && actual != null ? actual - planned : null;
  const delay = data?.finish_variance_days ?? null;
  const baseline = data?.versions.find((v) => v.kind === "baseline") ?? null;
  const latest = data?.versions.find((v) => v.kind === "latest") ?? null;

  return (
    <BlockShell
      title="Progress: planned vs actual"
      subtitle={
        data ? `Against baseline ${data.version_label} · data date ${fmtP6Date(data.data_date)}` : undefined
      }
      state={state}
      unavailable="Lock a baseline in Programme > Baselines — planned progress has nothing to measure against until then."
    >
      {data && (
        <>
          <div className="pvp-top">
            <div className="pvp-bars">
              {(
                [
                  ["Planned", planned, "pvp-fill-planned", "Baseline plan, work due before the data date"],
                  ["Actual", actual, "pvp-fill-actual", "Current schedule, work earned to date"],
                ] as const
              ).map(([label, value, fill, hint]) => (
                <div className="pvp-row" key={label}>
                  <div className="pvp-label">
                    <span className="pvp-label-name">{label}</span>
                    <span className="pvp-label-hint">{hint}</span>
                  </div>
                  <div
                    className="pvp-track"
                    role="meter"
                    aria-label={`${label} complete`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={value ?? 0}
                  >
                    <div className={`pvp-fill ${fill}`} style={{ width: `${Math.min(Math.max(value ?? 0, 0), 100)}%` }} />
                    {label === "Actual" && planned != null && (
                      <div className="pvp-marker" style={{ left: `${Math.min(planned, 100)}%` }} title="Planned" />
                    )}
                  </div>
                  <div className="pvp-value num">{fmtPct(value)}</div>
                </div>
              ))}
              {gap != null && (
                <div className="pvp-gap">
                  {Math.abs(gap) < 0.05
                    ? "Exactly on the baseline plan."
                    : `${fmtNum(Math.abs(gap), 1)} percentage points ${gap < 0 ? "behind" : "ahead of"} the baseline plan.`}
                </div>
              )}
            </div>

            <div className="pvp-kpi">
              <div className="pvp-kpi-label">Forecast finish delay</div>
              <div className={`pvp-kpi-value num tone-${delay == null ? "neutral" : delay > 30 ? "crit" : delay > 0 ? "warn" : "good"}`}>
                {delay == null ? "—" : delay <= 0 ? "None" : fmtMonths(delay)}
              </div>
              <div className="pvp-kpi-note">
                {delay == null
                  ? "No finish date to compare"
                  : `${delay > 0 ? "+" : ""}${delay} days · ${fmtP6Date(latest?.finish)} vs ${fmtP6Date(baseline?.finish)}`}
              </div>
            </div>

            <div className="pvp-kpi">
              <div className="pvp-kpi-label">Schedule performance</div>
              <div className={`pvp-kpi-value num tone-${spiTone(data.spi)}`}>{fmtNum(data.spi)}</div>
              <div className="pvp-kpi-note">SPI = actual ÷ planned · {spiNote(data.spi)}</div>
            </div>
          </div>

          <div className="table-wrap">
            <table className="pvp-versions">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>File</th>
                  <th>Data date</th>
                  <th>Start</th>
                  <th>Finish</th>
                  <th>Duration</th>
                  <th>Milestones (remaining)</th>
                  <th>Tasks (remaining)</th>
                  <th>Max WBS level</th>
                </tr>
              </thead>
              <tbody>
                {data.versions.map((v) => (
                  <tr key={v.kind}>
                    <td>
                      <span className={`pvp-swatch ${v.kind === "baseline" ? "pvp-fill-planned" : "pvp-fill-actual"}`} />
                      <span className="subname">{v.kind === "baseline" ? "Baseline (planned)" : "Latest (actual)"}</span>
                      <div className="actid">{v.label ?? "—"}</div>
                    </td>
                    <td className="mono pvp-file" title={v.filename ?? undefined}>
                      {v.filename ?? "—"}
                    </td>
                    <td className="num">{fmtP6Date(v.data_date)}</td>
                    <td className="num">{fmtP6Date(v.start)}</td>
                    <td className="num">{fmtP6Date(v.finish)}</td>
                    <td className="num">{fmtMonths(daysBetween(v.start, v.finish))}</td>
                    <td className="num">
                      {fmtNum(v.milestones_total, 0)} ({fmtNum(v.milestones_remaining, 0)})
                    </td>
                    <td className="num">
                      {fmtNum(v.tasks_total, 0)} ({fmtNum(v.tasks_remaining, 0)})
                    </td>
                    <td className="num">{v.max_wbs_level || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="report-note">
            Baseline remaining counts what the baseline still had open at the current data date; latest remaining
            is what is actually still open. {data.basis}.
          </p>
        </>
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
      unavailable="Lock a baseline in Programme > Baselines to generate the planned-value curve."
    >
      {data && (
        <div className="report-chart">
          <ScurveChart series={data.series} />
        </div>
      )}
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
      hint={countLabel(data?.length, "branch")}
      state={state}
      unavailable="No activities in the current programme."
    >
      <div className="table-wrap">
        <table className="report-wbs">
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
                <td>
                  {/* Earned-to-date, so it wears the S-curve's EV hue (--good). */}
                  <div className="report-meter">
                    <div
                      className="report-meter-track"
                      role="meter"
                      aria-label={`${r.branch} complete`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(r.pct * 10) / 10}
                    >
                      <div className="report-meter-fill report-fill-good" style={{ width: `${Math.min(Math.max(r.pct, 0), 100)}%` }} />
                    </div>
                    <span className="report-meter-value num">{fmtPct(r.pct)}</span>
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
      hint={countLabel(data?.length, "activity")}
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
                <td className="num">{fmtNum(toDays(a.remaining_duration_hours ?? 0, a), 1)}d</td>
                <td className="num">{fmtP6Date(a.early_start)}</td>
                <td className="num">{fmtP6Date(a.early_finish)}</td>
                <td className="num">
                  <FloatBadge days={toDays(a.total_float_hours, a)} />
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
      hint={countLabel(data?.paths.length, "path")}
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
      hint={countLabel(rows.length, "row")}
      state={state}
      unavailable="Lock a baseline in Programme > Baselines to compare dates against it."
    >
      {data && (
        <>
          <div className="report-top">
            <div className="report-panel">
              <div className="report-panel-title">Finish date against baseline</div>
              {/* Late reads through --warn, early through --good (the Schedule
                  Simulation convention); red is kept for the critical rows below. */}
              <DistributionStrip
                label="Activities by finish variance"
                unit="activities"
                segments={[
                  { label: "Behind", value: data.summary.behind, fill: "warn" },
                  { label: "On track", value: data.summary.on_track, fill: "neutral" },
                  { label: "Ahead", value: data.summary.ahead, fill: "good" },
                ]}
              />
            </div>
            <Metric
              label="Project finish"
              value={fmtDays(data.summary.project_finish_variance_days)}
              note={`Forecast ${fmtP6Date(data.summary.forecast_finish)}`}
              tone={slipTone(data.summary.project_finish_variance_days)}
            />
            <Metric
              label="Worst slip"
              value={fmtDays(data.summary.worst_slip_days)}
              note={`${data.summary.critical_slip_count} critical ${data.summary.critical_slip_count === 1 ? "activity" : "activities"} slipping`}
              tone={(data.summary.worst_slip_days ?? 0) > 0 ? "warn" : "neutral"}
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
      unavailable="Needs two schedule updates to compare — upload the next .xer from Programs."
    >
      {data && (
        <div className="report-section">
          <BarList
            rows={[
              { label: "Activities added", value: data.summary.activities_added },
              { label: "Activities removed", value: data.summary.activities_removed },
              { label: "Activities modified", value: data.summary.activities_modified },
              { label: "Activity IDs changed", value: data.summary.activities_renamed },
              {
                label: "Logic changed",
                value:
                  data.summary.relationships_added +
                  data.summary.relationships_removed +
                  data.summary.relationships_modified,
                note: `${data.summary.relationships_added} added, ${data.summary.relationships_removed} removed, ${data.summary.relationships_modified} retyped`,
              },
              { label: "Criticality changed", value: data.summary.criticality_changes },
            ]}
          />
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
      hint={countLabel(data?.length, "activity")}
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
                  <FloatBadge days={toDays(a.total_float_hours, a)} />
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
      hint={countLabel(data?.length, "risk")}
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

const DAY_MS = 86_400_000;

/** P10–P90 finish range on a date axis: the shaded band is the 80% spread,
 *  each percentile a tick. Labels alternate above and below the track so
 *  neighbouring percentiles (P80 and P90 often sit days apart) never collide;
 *  the exact dates are in the tiles underneath, not only on hover. */
function FinishRange({ data }: { data: MonteCarloResult }) {
  const points = (
    [
      ["P10", data.project_finish_p10, "below"],
      ["P50", data.project_finish_p50, "above"],
      ["P80", data.project_finish_p80, "below"],
      ["P90", data.project_finish_p90, "above"],
    ] as const
  ).map(([label, iso, row]) => ({ label, iso, row, t: new Date(iso).getTime() }));
  if (points.some((p) => Number.isNaN(p.t))) return null;

  const first = Math.min(...points.map((p) => p.t));
  const last = Math.max(...points.map((p) => p.t));
  const pad = Math.max((last - first) * 0.08, 7 * DAY_MS);
  const lo = first - pad;
  const hi = last + pad;
  const x = (t: number) => ((t - lo) / (hi - lo)) * 100;

  // Month gridlines, thinned to at most five labelled ticks, and kept off the
  // very edges so a label never hangs outside the strip.
  const months: number[] = [];
  const start = new Date(lo);
  for (
    let t = Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1);
    t <= hi;
    t = Date.UTC(new Date(t).getUTCFullYear(), new Date(t).getUTCMonth() + 1, 1)
  ) {
    months.push(t);
  }
  const step = Math.max(1, Math.ceil(months.length / 5));
  const ticks = months.filter((t, i) => i % step === 0 && x(t) > 5 && x(t) < 95);
  const spreadDays = Math.round((last - first) / DAY_MS);

  const labelRow = (row: "above" | "below") => (
    <div className={`report-range-labels is-${row}`} aria-hidden="true">
      {points
        .filter((p) => p.row === row)
        .map((p) => (
          <span key={p.label} style={{ left: `${x(p.t)}%` }}>
            {p.label}
          </span>
        ))}
    </div>
  );

  return (
    <div className="report-section">
      <div className="report-panel">
        <div className="report-panel-title">
          Finish date range <span className="report-panel-sub">P10 to P90 spread: {spreadDays} days</span>
        </div>
        <div
          className="report-range"
          role="img"
          aria-label={`Probabilistic finish: ${points.map((p) => `${p.label} ${fmtP6Date(p.iso)}`).join(", ")}`}
        >
          {labelRow("above")}
          <div className="report-range-track">
            {ticks.map((t) => (
              <span key={t} className="report-range-grid" style={{ left: `${x(t)}%` }} />
            ))}
            <span className="report-range-band" style={{ left: `${x(first)}%`, width: `${x(last) - x(first)}%` }} />
            {points.map((p) => (
              <span
                key={p.label}
                className={`report-range-tick${p.label === "P50" ? " is-median" : ""}`}
                style={{ left: `${x(p.t)}%` }}
                title={`${p.label}: ${fmtP6Date(p.iso)}`}
              />
            ))}
          </div>
          {labelRow("below")}
          <div className="report-range-axis" aria-hidden="true">
            {ticks.map((t) => (
              <span key={t} style={{ left: `${x(t)}%` }}>
                {fmtP6Date(new Date(t).toISOString()).slice(3)}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
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
          <FinishRange data={data} />
          <div className="report-kpis report-kpis-dates">
            {(
              [
                ["P10", data.project_finish_p10, 10],
                ["P50", data.project_finish_p50, 50],
                ["P80", data.project_finish_p80, 80],
                ["P90", data.project_finish_p90, 90],
              ] as const
            ).map(([label, iso, pct]) => (
              <Metric key={label} label={label} value={fmtP6Date(iso)} note={`${pct}% of runs finish by then`} />
            ))}
          </div>
          <p className="report-note">
            {data.iterations.toLocaleString("en-US")} iterations. The simulation&rsquo;s forward pass does not
            apply calendars, so these dates are indicative of spread rather than exact working dates.
          </p>
        </>
      )}
    </BlockShell>
  );
}

const DCMA_LABEL: Record<DcmaReport["overall_status"], string> = { pass: "Pass", warn: "Warn", fail: "Fail" };
const DCMA_CHIP: Record<DcmaReport["overall_status"], string> = {
  pass: "chip-good",
  warn: "chip-warn",
  fail: "chip-crit",
};
const DCMA_TONE: Record<DcmaReport["overall_status"], Tone> = { pass: "good", warn: "warn", fail: "crit" };

function DcmaBlock({ project }: BlockContext) {
  const { data, state } = useBlockData<DcmaReport>(
    () => api.get<DcmaReport>(`/projects/${project.id}/dcma`),
    [project.id],
  );

  return (
    <BlockShell
      title="DCMA 14-point check"
      subtitle={data ? `Score ${fmtNum(data.overall_score, 0)} / 100 over ${data.in_scope} activities` : undefined}
      meta={data ? <span className={`chip ${DCMA_CHIP[data.overall_status]}`}>{DCMA_LABEL[data.overall_status]}</span> : undefined}
      hint={countLabel(data?.checks.filter((c) => c.scored !== false).length, "check")}
      state={state}
      unavailable="Import a schedule to run the quality checks."
    >
      {data && (
        <div className="report-top is-single">
          <div className="report-panel">
            <div className="report-panel-title">Checks by result</div>
            <DistributionStrip
              label="DCMA checks by result"
              unit="checks"
              segments={[
                { label: "Pass", value: data.checks.filter((c) => c.scored !== false && c.status === "pass").length, fill: "good" },
                { label: "Warn", value: data.checks.filter((c) => c.scored !== false && c.status === "warn").length, fill: "warn" },
                { label: "Fail", value: data.checks.filter((c) => c.scored !== false && c.status === "fail").length, fill: "crit" },
                {
                  label: "Not tracked",
                  value: data.checks.filter((c) => c.scored !== false && c.status === "not_tracked").length,
                  fill: "neutral",
                },
              ]}
            />
          </div>
          <Metric
            label="Overall score"
            value={`${fmtNum(data.overall_score, 0)} / 100`}
            note={`${DCMA_LABEL[data.overall_status]} · ${data.in_scope} of ${data.total_activities} activities in scope`}
            tone={DCMA_TONE[data.overall_status]}
          />
        </div>
      )}
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
            {(data?.checks ?? []).filter((c) => c.scored !== false).map((c) => (
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
                    {c.status === "not_tracked" ? "Not tracked" : DCMA_LABEL[c.status]}
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
