"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PageState } from "@/components/PageShell";
import { EmptyState } from "@/components/EmptyState";
import { UploadScheduleIllo } from "@/components/illustrations";
import { PortfolioTimeline } from "@/components/portfolio/PortfolioTimeline";
import { ArrowRightIcon, ChevronDownIcon, ChevronUpIcon, XIcon } from "@/components/icons";
import { fmtP6Date } from "@/components/reporting/format";
import { FoldCard } from "@/components/reporting/collapse";
import { api, ApiError } from "@/lib/api";
import { criticalityChip } from "@/lib/criticality";
import {
  DENSITY_COLORS,
  DENSITY_LABELS,
  monthIndex,
  monthKey,
  monthLabel,
  PROGRESS_LABEL,
  PROGRESS_ROWS,
  QUALITY_ROWS,
  RISK_ROWS,
  spiTone,
  todayMonthIndex,
  varianceMonths,
  type Portfolio,
  type PortfolioActivity,
  type PortfolioMonthActivities,
  type PortfolioProject,
} from "@/lib/portfolio";
import { useProjectContext } from "@/lib/project-context";

type Window = "1m" | "3m" | "6m" | "1y" | "2y" | "4y" | "all" | "custom";
type VerdictFilter =
  | { kind: "progress"; key: string; label: string }
  | { kind: "risk"; key: string; label: string }
  | { kind: "quality"; key: string; label: string };
type SortKey = "name" | "spi" | "planned_pct" | "actual_pct" | "forecast_finish" | "variance" | "quality_score" | "critical";

const WINDOWS: { key: Window; label: string; months: number | null }[] = [
  { key: "1m", label: "1M", months: 1 },
  { key: "3m", label: "3M", months: 3 },
  { key: "6m", label: "6M", months: 6 },
  { key: "1y", label: "1Y", months: 12 },
  { key: "2y", label: "2Y", months: 24 },
  { key: "4y", label: "4Y", months: 48 },
  { key: "all", label: "All", months: null },
  { key: "custom", label: "Custom", months: null },
];

function windowRange(mode: Window, minIdx: number, maxIdx: number): [number, number] {
  const span = WINDOWS.find((w) => w.key === mode)?.months;
  if (!span || maxIdx - minIdx + 1 <= span) return [minIdx, maxIdx];
  // A quarter of the window behind today, the rest ahead — clamped onto the data.
  let lo = todayMonthIndex() - Math.floor(span / 4);
  lo = Math.max(minIdx, Math.min(lo, maxIdx - span + 1));
  return [lo, lo + span - 1];
}

function sortValue(p: PortfolioProject, key: SortKey): number | string {
  switch (key) {
    case "name":
      return p.name.toLowerCase();
    case "spi":
      return p.spi ?? -1;
    case "planned_pct":
      return p.planned_pct ?? -1;
    case "actual_pct":
      return p.actual_pct ?? -1;
    case "forecast_finish":
      return p.forecast_finish ?? "";
    case "variance":
      return p.finish_variance_days ?? -99999;
    case "quality_score":
      return p.quality_score ?? -1;
    case "critical":
      return p.critical_count;
  }
}

function pct(v: number | null): string {
  return v == null ? "—" : `${v.toFixed(1)}%`;
}

export default function PortfolioDashboardPage() {
  const router = useRouter();
  const { selectProject } = useProjectContext();
  const [data, setData] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [verdict, setVerdict] = useState<VerdictFilter | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "name", dir: 1 });
  const [windowMode, setWindowMode] = useState<Window>("2y");
  // Custom window, as <input type="month"> values ("YYYY-MM").
  const [customFrom, setCustomFrom] = useState(() => monthKey(todayMonthIndex() - 1));
  const [customTo, setCustomTo] = useState(() => monthKey(todayMonthIndex() + 5));
  const [showDensity, setShowDensity] = useState(true);
  const [drill, setDrill] = useState<{ project: PortfolioProject; month: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Portfolio>("/portfolio")
      .then((d) => !cancelled && setData(d))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : "Failed to load the portfolio."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const projects = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.projects ?? []).filter((p) => {
      if (q && !p.name.toLowerCase().includes(q) && !p.code.toLowerCase().includes(q)) return false;
      if (!verdict) return true;
      if (!p.has_schedule) return false;
      if (verdict.kind === "progress") return p.progress === verdict.key;
      if (verdict.kind === "risk") return p.risk === verdict.key;
      return p.quality === verdict.key;
    });
  }, [data, search, verdict]);

  const sorted = useMemo(
    () =>
      [...projects].sort((a, b) => {
        const va = sortValue(a, sort.key);
        const vb = sortValue(b, sort.key);
        return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
      }),
    [projects, sort],
  );

  // The portfolio row follows the filter: the filtered projects' months, summed.
  const portfolioMonths = useMemo(() => {
    if (!data) return [];
    if (!verdict && !search.trim()) return data.months;
    const sums = new Map<string, { month: string; score: number; tasks: number; critical: number; delay_drivers: number }>();
    for (const p of projects)
      for (const m of p.months) {
        const s = sums.get(m.month) ?? { month: m.month, score: 0, tasks: 0, critical: 0, delay_drivers: 0 };
        s.score += m.score;
        s.tasks += m.tasks;
        s.critical += m.critical;
        s.delay_drivers += m.delay_drivers;
        sums.set(m.month, s);
      }
    return [...sums.values()].sort((a, b) => a.month.localeCompare(b.month));
  }, [data, projects, verdict, search]);

  const range = useMemo<[number, number] | null>(() => {
    const keys = [...portfolioMonths.map((m) => m.month), ...projects.flatMap((p) => p.months.map((m) => m.month))];
    if (keys.length === 0) return null;
    const idx = keys.map(monthIndex);
    if (windowMode === "custom" && /^\d{4}-\d{2}$/.test(customFrom) && /^\d{4}-\d{2}$/.test(customTo)) {
      const a = monthIndex(customFrom);
      const b = monthIndex(customTo);
      return [Math.min(a, b), Math.max(a, b)];
    }
    return windowRange(windowMode, Math.min(...idx), Math.max(...idx));
  }, [portfolioMonths, projects, windowMode, customFrom, customTo]);

  const kpis = useMemo(() => {
    const scheduled = (data?.projects ?? []).filter((p) => p.has_schedule);
    const quality = scheduled.filter((p) => p.quality_score != null);
    return {
      projects: data?.projects.length ?? 0,
      scheduled: scheduled.length,
      activities: scheduled.reduce((n, p) => n + p.activity_count, 0),
      critical: scheduled.reduce((n, p) => n + p.critical_count, 0),
      negative: scheduled.reduce((n, p) => n + p.negative_float_count, 0),
      quality: quality.length ? quality.reduce((n, p) => n + (p.quality_score ?? 0), 0) / quality.length : null,
    };
  }, [data]);

  function toggleSort(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === "name" ? 1 : -1 }));
  }

  function openProject(p: PortfolioProject) {
    selectProject(p.id);
    router.push("/dashboard");
  }

  if (loading) return <PageState kind="loading" section="Projects" title="Portfolio Dashboard" />;
  if (error) return <PageState kind="error" section="Projects" title="Portfolio Dashboard" message={error} />;

  const summary = data?.summary;
  const scheduledCount = kpis.scheduled || 1;

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">Projects</span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Portfolio Dashboard</div>
            <div className="page-desc">
              Every project side by side — schedule performance, quality, and where criticality concentrates month by
              month
            </div>
          </div>
        </div>

        {!data || kpis.scheduled === 0 ? (
          <div className="card">
            <EmptyState
              art={<UploadScheduleIllo />}
              title="No programmes in the portfolio yet"
              body="Import a Primavera P6 .xer into a project from Programs and it appears here."
              action={
                <Link className="btn btn-primary btn-sm" href="/project-files">
                  Go to Programs
                </Link>
              }
            />
          </div>
        ) : (
          <>
            {/* ---- headline numbers ---- */}
            <div className="kpi-row pf-kpis">
              <div className="card kpi">
                <span className="kpi-label">Projects</span>
                <span className="kpi-value">{kpis.projects}</span>
                <span className="kpi-sub">{kpis.scheduled} with a programme</span>
              </div>
              <div className="card kpi">
                <span className="kpi-label">Activities</span>
                <span className="kpi-value">{kpis.activities.toLocaleString()}</span>
                <span className="kpi-sub">across the current programmes</span>
              </div>
              <div className="card kpi">
                <span className="kpi-label">Critical activities</span>
                <span className="kpi-value">{kpis.critical.toLocaleString()}</span>
                <span className="kpi-sub">{kpis.negative.toLocaleString()} on negative float</span>
              </div>
              <div className="card kpi">
                <span className="kpi-label">Average quality score</span>
                <span className="kpi-value">{kpis.quality == null ? "—" : kpis.quality.toFixed(0)}</span>
                <span className="kpi-sub">DCMA 14-point, out of 100</span>
              </div>
            </div>

            {/* ---- overall status ---- */}
            <div className="card pf-status">
              <div className="card-head">
                <div>
                  <div className="card-title">Overall status</div>
                  <div className="card-title-sub">Click a row to filter the scorecard and timelines</div>
                </div>
                {verdict && (
                  <button className="btn btn-secondary btn-sm" onClick={() => setVerdict(null)}>
                    <XIcon className="icon" /> Clear filter: {verdict.label}
                  </button>
                )}
              </div>
              <div className="pf-status-grid">
                <StatusPanel
                  title="Progress"
                  rows={PROGRESS_ROWS.map((r) => ({
                    ...r,
                    count: summary?.progress[r.key] ?? 0,
                    note:
                      r.key === "behind" && summary?.behind_avg_overrun_pct
                        ? `${summary.behind_avg_overrun_pct.toFixed(1)}% avg overrun`
                        : undefined,
                  }))}
                  total={scheduledCount}
                  active={verdict?.kind === "progress" ? verdict.key : null}
                  onPick={(key, label) => setVerdict(verdict?.kind === "progress" && verdict.key === key ? null : { kind: "progress", key, label: `Progress ${label.toLowerCase()}` })}
                />
                <StatusPanel
                  title="Risk"
                  rows={RISK_ROWS.map((r) => ({ ...r, count: summary?.risk[r.key] ?? 0 }))}
                  total={scheduledCount}
                  active={verdict?.kind === "risk" ? verdict.key : null}
                  onPick={(key, label) => setVerdict(verdict?.kind === "risk" && verdict.key === key ? null : { kind: "risk", key, label: `${label} risk` })}
                />
                <StatusPanel
                  title="Quality"
                  rows={QUALITY_ROWS.map((r) => ({ ...r, count: summary?.quality[r.key] ?? 0 }))}
                  total={scheduledCount}
                  active={verdict?.kind === "quality" ? verdict.key : null}
                  onPick={(key, label) => setVerdict(verdict?.kind === "quality" && verdict.key === key ? null : { kind: "quality", key, label: `${label} quality` })}
                />
              </div>
            </div>

            {/* ---- scorecard ---- */}
            <div className="card pf-card">
              <div className="card-head">
                <div>
                  <div className="card-title">Portfolio scorecard</div>
                  <div className="card-title-sub">
                    {sorted.length} of {data.projects.length} projects · click a project to open its dashboard
                  </div>
                </div>
                <input
                  type="search"
                  className="pf-search"
                  placeholder="Search by name or code…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="table-wrap">
                <table className="pf-table">
                  <thead>
                    <tr>
                      <SortTh label="Project" k="name" sort={sort} onSort={toggleSort} />
                      <SortTh label="SPI" k="spi" sort={sort} onSort={toggleSort} right />
                      <SortTh label="Planned" k="planned_pct" sort={sort} onSort={toggleSort} right />
                      <SortTh label="Actual" k="actual_pct" sort={sort} onSort={toggleSort} right />
                      <th>Actual start</th>
                      <SortTh label="Finish" k="forecast_finish" sort={sort} onSort={toggleSort} />
                      <SortTh label="vs baseline" k="variance" sort={sort} onSort={toggleSort} />
                      <SortTh label="Quality" k="quality_score" sort={sort} onSort={toggleSort} right />
                      <th>Status</th>
                      <SortTh label="Critical" k="critical" sort={sort} onSort={toggleSort} right />
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <button type="button" className="pf-project-link" onClick={() => openProject(p)}>
                            <span className="pf-project-name">{p.name}</span>
                            <span className="pf-project-code mono">{p.code}</span>
                          </button>
                        </td>
                        {p.has_schedule ? (
                          <>
                            <td className="num" style={{ textAlign: "right" }}>
                              <span className="pf-dot" style={{ background: spiTone(p.spi) }} />
                              {p.spi?.toFixed(2) ?? "—"}
                            </td>
                            <td className="num" style={{ textAlign: "right" }}>
                              {pct(p.planned_pct)}
                            </td>
                            <td className="num" style={{ textAlign: "right" }}>
                              {pct(p.actual_pct)}
                            </td>
                            <td className="num">{fmtP6Date(p.actual_start)}</td>
                            <td className="num">{fmtP6Date(p.forecast_finish)}</td>
                            <td>
                              <div className="num">{fmtP6Date(p.baseline_finish)}</div>
                              <div
                                className="pf-variance"
                                style={{
                                  color:
                                    (p.finish_variance_days ?? 0) > 0 ? "var(--crit)" : "var(--text-muted)",
                                }}
                              >
                                {varianceMonths(p.finish_variance_days)}
                              </div>
                            </td>
                            <td className="num" style={{ textAlign: "right" }}>
                              {p.quality_score?.toFixed(0) ?? "—"}
                            </td>
                            <td>
                              <div className="pf-verdicts">
                                <span className={`chip ${p.progress === "behind" ? "chip-crit" : p.progress === "slightly_behind" ? "chip-warn" : p.progress === "no_data" ? "chip-neutral" : "chip-good"}`}>
                                  {PROGRESS_LABEL[p.progress]}
                                </span>
                                <span className={`chip ${p.risk === "HIGH" ? "chip-crit" : p.risk === "MEDIUM" ? "chip-warn" : "chip-good"}`}>
                                  {p.risk.charAt(0) + p.risk.slice(1).toLowerCase()} risk
                                </span>
                              </div>
                            </td>
                            <td className="num" style={{ textAlign: "right" }}>
                              {p.critical_count.toLocaleString()}
                            </td>
                          </>
                        ) : (
                          <td colSpan={9} style={{ color: "var(--text-muted)" }}>
                            No programme imported yet
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ---- timelines ---- */}
            <div className="card pf-card">
              <div className="card-head">
                <div>
                  <div className="card-title">Portfolio timelines</div>
                  <div className="card-title-sub">
                    Monthly criticality density — the summed Criticality Scores of the work active each month. Click
                    a month for its activities.
                  </div>
                </div>
                <div className="pf-tl-controls">
                  <div className="segmented" role="group" aria-label="Time window">
                    {WINDOWS.map((w) => (
                      <button
                        key={w.key}
                        className={windowMode === w.key ? "active" : ""}
                        onClick={() => setWindowMode(w.key)}
                        title={w.months ? `${w.months} month${w.months > 1 ? "s" : ""}, from around today` : undefined}
                      >
                        {w.label}
                      </button>
                    ))}
                  </div>
                  {windowMode === "custom" && (
                    <div className="pf-custom-range">
                      <label>
                        <span>From</span>
                        <input type="month" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} />
                      </label>
                      <label>
                        <span>To</span>
                        <input type="month" value={customTo} onChange={(e) => setCustomTo(e.target.value)} />
                      </label>
                    </div>
                  )}
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
              </div>
              {range ? (
                <>
                  <PortfolioTimeline
                    projects={sorted}
                    portfolio={portfolioMonths}
                    range={range}
                    showDensity={showDensity}
                    onMonthClick={(project, month) => setDrill({ project, month })}
                  />
                  {showDensity && (
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
                  )}
                </>
              ) : (
                <p className="empty-state">No project matches the filter.</p>
              )}
            </div>

            {/* ---- top critical ---- */}
            <FoldCard
              className="pf-card"
              title="Most critical activities"
              subtitle="Highest Criticality Scores across the portfolio, unfinished work only"
              hint={`${data.top_activities.length} activities`}
            >
              <ActivityTable rows={data.top_activities} showProject />
            </FoldCard>
          </>
        )}
      </div>

      {drill && (
        <MonthDrill
          project={drill.project}
          month={drill.month}
          onClose={() => setDrill(null)}
          onOpen={() => openProject(drill.project)}
        />
      )}
    </>
  );
}

function StatusPanel({
  title,
  rows,
  total,
  active,
  onPick,
}: {
  title: string;
  rows: { key: string; label: string; tone: string; count: number; note?: string }[];
  total: number;
  active: string | null;
  onPick: (key: string, label: string) => void;
}) {
  return (
    <div className="pf-panel">
      <div className="pf-panel-title">{title}</div>
      {rows.map((r) => (
        <button
          key={r.key}
          type="button"
          className={`pf-panel-row${active === r.key ? " is-on" : ""}`}
          onClick={() => onPick(r.key, r.label)}
          disabled={r.count === 0 && active !== r.key}
        >
          <span className="pf-panel-label">{r.label}</span>
          <span className="pf-panel-value">
            <span className="pf-panel-count">
              {r.count}
              {r.note && <span className="pf-panel-note">{r.note}</span>}
            </span>
            <span className="pf-panel-bar">
              <span style={{ width: `${(r.count / total) * 100}%`, background: r.tone }} />
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}

function SortTh({
  label,
  k,
  sort,
  onSort,
  right,
}: {
  label: string;
  k: SortKey;
  sort: { key: SortKey; dir: 1 | -1 };
  onSort: (k: SortKey) => void;
  right?: boolean;
}) {
  const on = sort.key === k;
  return (
    <th style={right ? { textAlign: "right" } : undefined} aria-sort={on ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" className={`pf-sort${on ? " is-on" : ""}`} onClick={() => onSort(k)}>
        {label}
        {on &&
          (sort.dir === 1 ? (
            <ChevronUpIcon className="icon" style={{ width: 12, height: 12 }} />
          ) : (
            <ChevronDownIcon className="icon" style={{ width: 12, height: 12 }} />
          ))}
      </button>
    </th>
  );
}

function ActivityTable({ rows, showProject = false }: { rows: PortfolioActivity[]; showProject?: boolean }) {
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

function breakdownTitle(a: PortfolioActivity): string {
  const b = a.criticality_breakdown;
  if (!b) return "";
  return `Total float ${b.total_float} · Duration ${b.duration} · Free float ${b.free_float} · Site risk ${b.site_risk}`;
}

function MonthDrill({
  project,
  month,
  onClose,
  onOpen,
}: {
  project: PortfolioProject;
  month: string;
  onClose: () => void;
  onOpen: () => void;
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
          <button type="button" className="btn btn-primary btn-sm" onClick={onOpen}>
            Open {project.code} dashboard <ArrowRightIcon className="icon" />
          </button>
        </div>
      </div>
    </div>
  );
}
