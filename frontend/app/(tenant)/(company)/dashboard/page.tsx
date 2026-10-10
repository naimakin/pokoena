"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageState } from "@/components/PageShell";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type {
  DashboardLayout,
  DashboardSummary,
  DashboardThemeKey,
  DashboardWidgetConfig,
  DashboardWidgetKey,
  ProgressCurve,
  ProjectAnalytics,
  ProjectHealth,
  RiskHighlight,
} from "@/lib/types";
import { AlertTriangleIcon, BellIcon, CheckIcon, SettingsIcon } from "@/components/icons";
import {
  WIDGET_REGISTRY,
  WIDGET_ORDER,
  type CurveStatus,
  type WidgetContext,
} from "@/components/dashboard/DashboardWidgets";
import { DashboardConfigModal } from "@/components/dashboard/DashboardConfigModal";
import { KpiStrip, type AnalyticsStatus } from "@/components/dashboard/AnalyticsWidgets";
import { NoProjectIllo } from "@/components/illustrations";
import { fmtP6Date } from "@/components/reporting/format";

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const diffMs = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}

const DEFAULT_LAYOUT_WIDGETS: DashboardWidgetConfig[] = WIDGET_ORDER.map((key, i) => ({
  key,
  order: i,
  enabled: true,
  options: {},
}));

export default function DashboardPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();

  const [layout, setLayout] = useState<DashboardLayout | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [health, setHealth] = useState<ProjectHealth | null>(null);
  const [risks, setRisks] = useState<RiskHighlight[] | null>(null);
  const [curve, setCurve] = useState<ProgressCurve | null>(null);
  const [curveStatus, setCurveStatus] = useState<CurveStatus>("idle");
  const [analytics, setAnalytics] = useState<ProjectAnalytics | null>(null);
  const [analyticsStatus, setAnalyticsStatus] = useState<AnalyticsStatus>("idle");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCloseWarning, setShowCloseWarning] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  // Auto-open the configure modal once per project when no layout is saved yet.
  const firstRunPromptedFor = useRef<string | null>(null);

  // A layout the user never saved is shown in the recommended WIDGET_ORDER
  // (progress curve under the KPI row, Health beside Top Risks); a saved one
  // keeps exactly the order the user chose. The configure modal starts from
  // the same list, so what it shows matches the page.
  const widgets = useMemo<DashboardWidgetConfig[]>(() => {
    const base = layout?.widgets ?? DEFAULT_LAYOUT_WIDGETS;
    if (layout && !layout.is_default) return base;
    const rank = (key: DashboardWidgetKey) => {
      const i = WIDGET_ORDER.indexOf(key);
      return i < 0 ? WIDGET_ORDER.length : i;
    };
    return [...base].sort((a, b) => rank(a.key) - rank(b.key)).map((w, i) => ({ ...w, order: i }));
  }, [layout]);

  const enabledKeys = useMemo<DashboardWidgetKey[]>(
    () =>
      widgets
        .filter((w) => w.enabled)
        .sort((a, b) => a.order - b.order)
        .map((w) => w.key),
    [widgets],
  );

  const load = useCallback(async () => {
    if (!project) {
      setLayout(null);
      setSummary(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // The layout is a single small row; once it's in, every widget's request
      // goes out at the same time — the summary no longer holds the rest back.
      const layoutRes = await api.get<DashboardLayout>(`/dashboard/layout?project_id=${project.id}`);
      setLayout(layoutRes);
      if (layoutRes.is_default && firstRunPromptedFor.current !== project.id) {
        firstRunPromptedFor.current = project.id;
        setConfigOpen(true);
      }

      const wanted = new Set(layoutRes.widgets.filter((w) => w.enabled).map((w) => w.key));

      if (wanted.has("health-badge")) {
        api
          .get<ProjectHealth>(`/dashboard/health?project_id=${project.id}`)
          .then(setHealth)
          .catch(() => setHealth(null));
      }
      if (wanted.has("risk-top3")) {
        api
          .get<RiskHighlight[]>(`/dashboard/risk-highlights?project_id=${project.id}`)
          .then(setRisks)
          .catch(() => setRisks(null));
      }
      // Always: the KPI strip on top reads it too.
      setAnalyticsStatus("loading");
      api
        .get<ProjectAnalytics>(`/dashboard/analytics?project_id=${project.id}`)
        .then((res) => {
          setAnalytics(res);
          setAnalyticsStatus("ready");
        })
        .catch((err) => {
          setAnalytics(null);
          setAnalyticsStatus(err instanceof ApiError && err.status === 423 ? "locked" : "error");
        });
      if (wanted.has("s-curve")) {
        setCurveStatus("loading");
        api
          .get<ProgressCurve>(`/projects/${project.id}/evm/progress-curve`)
          .then((res) => {
            setCurve(res);
            setCurveStatus("ready");
          })
          .catch((err) => {
            setCurve(null);
            setCurveStatus(err instanceof ApiError && err.status === 423 ? "locked" : "error");
          });
      }
      setSummary(await api.get<DashboardSummary>(`/dashboard/summary?project_id=${project.id}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the dashboard.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    setHealth(null);
    setRisks(null);
    setCurve(null);
    setCurveStatus("idle");
    setAnalytics(null);
    setAnalyticsStatus("idle");
    load();
  }, [load]);

  async function handleRemind() {
    const periodId = summary?.active_period_id;
    if (!periodId) return;
    try {
      const result = await api.post<{ reminded: number }>(`/update-periods/${periodId}/remind`);
      showToast(`Reminder sent to ${result.reminded} non-responding subcontractor(s)`);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to send reminders.", "error");
    }
  }

  async function handleConfirmClose() {
    const periodId = summary?.active_period_id;
    if (!periodId) return;
    try {
      await api.post(`/update-periods/${periodId}/close`);
      showToast("Period closed.");
      setShowCloseWarning(false);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to close the period.", "error");
    }
  }

  async function handleSaveConfig(widgets: DashboardWidgetConfig[], theme: DashboardThemeKey) {
    if (!project) return;
    setSavingConfig(true);
    try {
      const saved = await api.put<DashboardLayout>("/dashboard/layout", {
        project_id: project.id,
        theme_key: theme,
        widgets,
      });
      setLayout(saved);
      setConfigOpen(false);
      showToast("Dashboard saved.");
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save the dashboard.", "error");
    } finally {
      setSavingConfig(false);
    }
  }

  if (loading) {
    return <PageState kind="loading" section={project?.name ?? "Dashboard"} title="Dashboard" />;
  }
  if (error) {
    return <PageState kind="error" section={project?.name ?? "Dashboard"} title="Dashboard" message={error} />;
  }
  if (!project) {
    return (
      <PageState
        kind="empty"
        section="Dashboard"
        title="Dashboard"
        emptyTitle="No project yet"
        message="Create a project from the project switcher in the top bar, then upload its schedule."
        art={<NoProjectIllo />}
      />
    );
  }

  const pendingCount = summary ? summary.orgs_total - summary.orgs_submitted : 0;
  const deadlineDays = daysUntil(summary?.deadline_at ?? null);

  const ctx: WidgetContext = {
    project,
    summary,
    health,
    risks,
    curve,
    curveStatus,
    deadlineDays,
    analytics,
    analyticsStatus,
  };

  const kpiKeys = enabledKeys.filter((k) => WIDGET_REGISTRY[k].span === "kpi");
  const blockKeys = enabledKeys.filter((k) => {
    const def = WIDGET_REGISTRY[k];
    return def.span !== "kpi" && !def.hidden?.(ctx);
  });
  // A six-column grid: thirds take two columns, halves three. Thirds that
  // don't fill a row of three widen — two left over become halves, one left
  // over takes the full row — and an odd half out takes the full row (the
  // grid packs densely, so a later half fills the gap beside an earlier one).
  const cellOf = new Map<DashboardWidgetKey, "third" | "half" | "full">();
  const thirds = blockKeys.filter((k) => WIDGET_REGISTRY[k].span === "third");
  const thirdsRest = thirds.length % 3;
  thirds.forEach((k, i) => {
    const inTail = i >= thirds.length - thirdsRest;
    cellOf.set(k, !inTail ? "third" : thirdsRest === 2 ? "half" : "full");
  });
  for (const k of blockKeys) {
    if (!cellOf.has(k)) cellOf.set(k, WIDGET_REGISTRY[k].span === "full" ? "full" : "half");
  }
  const halfKeys = blockKeys.filter((k) => cellOf.get(k) === "half");
  if (halfKeys.length % 2 === 1) cellOf.set(halfKeys[halfKeys.length - 1], "full");

  const inPeriod = Boolean(summary?.active_period_id);
  const currentUpdate = summary?.current_update ?? null;
  const pageDesc = inPeriod
    ? `${summary?.active_period_label ?? "Update period"} · subcontractor update period`
    : currentUpdate
      ? `Schedule ${currentUpdate.revision_label ?? "latest import"} · data date ${fmtP6Date(currentUpdate.data_date)}`
      : "No open update period and no schedule imported yet";

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project.name}
        </span>
        <div className="spacer" />
        {summary?.active_period_status && (
          <span className={`chip ${summary?.active_period_status === "open" ? "chip-good" : "chip-neutral"}`}>
            {summary?.active_period_label} {summary?.active_period_status === "open" ? "Open" : "Closed"}
          </span>
        )}
      </div>

      <div className="a-content" data-dash-theme={layout?.theme_key ?? "calm"}>
        <div className="page-head">
          <div>
            <div className="page-title">Dashboard</div>
            <div className="page-desc">{pageDesc}</div>
          </div>
          <div className="dash-actions">
            <button className="btn btn-secondary" onClick={() => setConfigOpen(true)}>
              <SettingsIcon className="icon" /> Configure
            </button>
            {/* Period actions only mean something while a period is running. */}
            {inPeriod && (
              <>
                <button className="btn btn-secondary" onClick={handleRemind}>
                  <BellIcon className="icon" /> Send Reminder
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => setShowCloseWarning(true)}
                  disabled={summary?.active_period_status !== "open"}
                >
                  <CheckIcon className="icon" /> Close &amp; Run Analysis
                </button>
              </>
            )}
          </div>
        </div>

        {showCloseWarning && (
          <div className="banner warn">
            <AlertTriangleIcon className="icon" />
            <span className="banner-text">
              <b>
                {pendingCount} of {summary?.orgs_total} scopes
              </b>{" "}
              haven&rsquo;t submitted yet. Closing now will freeze their activities at last-saved values.
            </span>
            <div className="banner-actions">
              <button className="btn btn-ghost btn-sm" onClick={() => setShowCloseWarning(false)}>
                Cancel
              </button>
              <button className="btn btn-danger btn-sm" onClick={handleConfirmClose}>
                Close anyway
              </button>
            </div>
          </div>
        )}

        {enabledKeys.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              No widgets selected. <button className="btn btn-ghost btn-sm" onClick={() => setConfigOpen(true)}>Configure the dashboard</button>
            </p>
          </div>
        ) : (
          <div className="dash-stack">
            {analytics && <KpiStrip a={analytics} />}
            {kpiKeys.length > 0 && (
              <div className="kpi-row">
                {kpiKeys.map((key) => (
                  <Fragment key={key}>{WIDGET_REGISTRY[key].render(ctx)}</Fragment>
                ))}
              </div>
            )}

            {blockKeys.length > 0 && (
              <div className="dash-grid">
                {blockKeys.map((key) => {
                  const def = WIDGET_REGISTRY[key];
                  const cell = cellOf.get(key) ?? "half";
                  const action = def.action ? def.action(ctx) : null;
                  const count = def.count ? def.count(ctx) : null;
                  return (
                    <section key={key} className={`card dash-card dash-cell-${cell}`}>
                      <div className="card-head">
                        <div>
                          <div className="card-title">
                            {def.title}
                            {count != null && <span className="card-count">{count}</span>}
                          </div>
                          <div className="card-title-sub">{def.description}</div>
                        </div>
                        {action}
                      </div>
                      <div className={`dash-card-body${def.pad ? " is-padded" : ""}`}>{def.render(ctx)}</div>
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      <DashboardConfigModal
        open={configOpen}
        initialWidgets={widgets}
        initialTheme={layout?.theme_key ?? "calm"}
        saving={savingConfig}
        onCancel={() => setConfigOpen(false)}
        onSave={handleSaveConfig}
      />
    </>
  );
}
