"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type {
  DashboardLayout,
  DashboardSummary,
  DashboardThemeKey,
  DashboardWidgetConfig,
  DashboardWidgetKey,
  EvmScurve,
  ProjectHealth,
  RiskHighlight,
} from "@/lib/types";
import { AlertTriangleIcon, BellIcon, CheckIcon, SettingsIcon } from "@/components/icons";
import {
  WIDGET_REGISTRY,
  WIDGET_ORDER,
  type WidgetContext,
} from "@/components/dashboard/DashboardWidgets";
import { DashboardConfigModal } from "@/components/dashboard/DashboardConfigModal";

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
  const [scurve, setScurve] = useState<EvmScurve | null>(null);
  const [scurveLocked, setScurveLocked] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCloseWarning, setShowCloseWarning] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  // Auto-open the configure modal once per project when no layout is saved yet.
  const firstRunPromptedFor = useRef<string | null>(null);

  const enabledKeys = useMemo<DashboardWidgetKey[]>(
    () =>
      (layout?.widgets ?? DEFAULT_LAYOUT_WIDGETS)
        .filter((w) => w.enabled)
        .sort((a, b) => a.order - b.order)
        .map((w) => w.key),
    [layout],
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
      const [layoutRes, summaryRes] = await Promise.all([
        api.get<DashboardLayout>(`/dashboard/layout?project_id=${project.id}`),
        api.get<DashboardSummary>(`/dashboard/summary?project_id=${project.id}`),
      ]);
      setLayout(layoutRes);
      setSummary(summaryRes);
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
      if (wanted.has("s-curve")) {
        setScurveLocked(false);
        api
          .get<EvmScurve>(`/projects/${project.id}/evm/scurve?granularity=monthly`)
          .then((res) => {
            setScurve(res);
            setScurveLocked(false);
          })
          .catch((err) => {
            setScurve(null);
            setScurveLocked(err instanceof ApiError && err.status === 423);
          });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the dashboard.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    setHealth(null);
    setRisks(null);
    setScurve(null);
    load();
  }, [load]);

  async function handleRemind() {
    const periodId = summary?.active_period_id;
    if (!periodId) return;
    try {
      const result = await api.post<{ reminded: number }>(`/update-periods/${periodId}/remind`);
      showToast(`Reminder sent to ${result.reminded} non-responding subcontractor(s)`);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to send reminders.");
    }
  }

  async function handleConfirmClose() {
    const periodId = summary?.active_period_id;
    if (!periodId) return;
    try {
      await api.post(`/update-periods/${periodId}/close`);
      showToast("Period closed. S-curve, EVM and Monte Carlo analysis ship in Phase 2.");
      setShowCloseWarning(false);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to close the period.");
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
      showToast(err instanceof ApiError ? err.message : "Failed to save the dashboard.");
    } finally {
      setSavingConfig(false);
    }
  }

  if (loading) {
    return (
      <div className="a-content">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="a-content">
        <p className="login-error" style={{ maxWidth: 420 }}>
          {error}
        </p>
      </div>
    );
  }
  if (!project) {
    return (
      <div className="a-content">
        <p className="page-desc">No projects yet — create one from the project switcher in the top bar.</p>
      </div>
    );
  }

  const pendingCount = summary ? summary.orgs_total - summary.orgs_submitted : 0;
  const deadlineDays = daysUntil(summary?.deadline_at ?? null);

  const ctx: WidgetContext = {
    project,
    summary,
    health,
    risks,
    scurve,
    scurveLocked,
    deadlineDays,
  };

  const kpiKeys = enabledKeys.filter((k) => WIDGET_REGISTRY[k].span === "kpi");
  const blockKeys = enabledKeys.filter((k) => WIDGET_REGISTRY[k].span !== "kpi");

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project.name} / <b>Dashboard</b>
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
            <div className="page-desc">{summary?.active_period_label ?? "No open update period"}</div>
          </div>
          <div style={{ display: "flex", gap: ".55rem" }}>
            <button className="btn btn-secondary" onClick={() => setConfigOpen(true)}>
              <SettingsIcon className="icon" /> Configure
            </button>
            <button className="btn btn-secondary" onClick={handleRemind} disabled={!summary?.active_period_id}>
              <BellIcon className="icon" /> Send Reminder
            </button>
            <button
              className="btn btn-primary"
              onClick={() => setShowCloseWarning(true)}
              disabled={!summary?.active_period_id || summary?.active_period_status !== "open"}
            >
              <CheckIcon className="icon" /> Close &amp; Run Analysis
            </button>
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
          <>
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
                  return (
                    <div key={key} className={`card${def.span === "full" ? " dash-cell-full" : ""}`}>
                      <div className="card-head">
                        <div>
                          <div className="card-title">{def.title}</div>
                          <div className="card-title-sub">{def.description}</div>
                        </div>
                      </div>
                      {def.pad ? <div style={{ padding: "1.1rem" }}>{def.render(ctx)}</div> : def.render(ctx)}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      <DashboardConfigModal
        open={configOpen}
        initialWidgets={layout?.widgets ?? DEFAULT_LAYOUT_WIDGETS}
        initialTheme={layout?.theme_key ?? "calm"}
        saving={savingConfig}
        onCancel={() => setConfigOpen(false)}
        onSave={handleSaveConfig}
      />
    </>
  );
}
