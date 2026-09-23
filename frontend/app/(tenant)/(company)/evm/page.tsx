"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { BaselineStatus, EvmScurve, EvmSummary, Project } from "@/lib/types";
import { CheckIcon, DownloadIcon, LockIcon, TrendingUpIcon } from "@/components/icons";
import { ScurveChart, selectStyle } from "@/components/ScurveChart";
import { ExpandableChartCard } from "@/components/ExpandableChartCard";

const GRANULARITIES = ["daily", "weekly", "monthly"] as const;
type Granularity = (typeof GRANULARITIES)[number];

function fmt(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

function indexColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "var(--text-muted)";
  if (v >= 0.95) return "var(--good)";
  if (v >= 0.85) return "var(--warn)";
  return "var(--crit)";
}

export default function EvmPage() {
  const { project } = useProjectContext();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [baselineStatus, setBaselineStatus] = useState<BaselineStatus | null>(null);
  const [summary, setSummary] = useState<EvmSummary | null>(null);
  const [scurve, setScurve] = useState<EvmScurve | null>(null);
  const [granularity, setGranularity] = useState<Granularity>("weekly");

  const [versionLabel, setVersionLabel] = useState("Target-1");
  const [locking, setLocking] = useState(false);
  const [lockError, setLockError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [superseding, setSuperseding] = useState(false);

  async function loadAll(p: Project) {
    const status = await api.get<BaselineStatus>(`/projects/${p.id}/evm/baseline`);
    setBaselineStatus(status);
    if (status.has_active) {
      const [summaryRes, scurveRes] = await Promise.all([
        api.get<EvmSummary>(`/projects/${p.id}/evm/summary`),
        api.get<EvmScurve>(`/projects/${p.id}/evm/scurve?granularity=${granularity}`),
      ]);
      setSummary(summaryRes);
      setScurve(scurveRes);
    } else {
      setSummary(null);
      setScurve(null);
    }
  }

  useEffect(() => {
    async function load() {
      if (!project) {
        setBaselineStatus(null);
        setSummary(null);
        setScurve(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        await loadAll(project);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load EVM data.");
      } finally {
        setLoading(false);
      }
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  useEffect(() => {
    if (!project || !baselineStatus?.has_active) return;
    api.get<EvmScurve>(`/projects/${project.id}/evm/scurve?granularity=${granularity}`).then(setScurve);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [granularity]);

  async function lockBaseline() {
    if (!project) return;
    setLocking(true);
    setLockError(null);
    try {
      await api.post(`/projects/${project.id}/evm/baseline`, { version_label: versionLabel });
      await loadAll(project);
    } catch (err) {
      setLockError(err instanceof ApiError ? err.message : "Failed to lock the baseline.");
    } finally {
      setLocking(false);
    }
  }

  async function supersedeBaseline() {
    if (!project || !baselineStatus?.active_baseline) return;
    setSuperseding(true);
    try {
      await api.delete(`/projects/${project.id}/evm/baseline/${baselineStatus.active_baseline.id}`);
      await loadAll(project);
    } catch (err) {
      setLockError(err instanceof ApiError ? err.message : "Failed to supersede the baseline.");
    } finally {
      setSuperseding(false);
    }
  }

  async function exportExcel() {
    if (!project) return;
    setExporting(true);
    try {
      const { blob, filename } = await api.getBlob(`/projects/${project.id}/evm/export`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename ?? `EVM_${project.code}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setLockError(err instanceof ApiError ? err.message : "Failed to export the workbook.");
    } finally {
      setExporting(false);
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

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>EVM / S-Curve</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">EVM / S-Curve</div>
            <div className="page-desc">Earned Value Management against a locked Performance Measurement Baseline</div>
          </div>
        </div>

        {!project ? (
          <div className="card">
            <p className="empty-state">No project yet — create one from the project switcher in the sidebar.</p>
          </div>
        ) : !baselineStatus?.has_active ? (
          <div className="card" style={{ padding: "1.25rem 1.1rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: ".85rem", maxWidth: 480 }}>
              <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
                <LockIcon className="icon" />
                <span style={{ fontWeight: 700, fontSize: ".9375rem" }}>No baseline locked yet</span>
              </div>
              <p style={{ fontSize: ".8125rem", color: "var(--text-secondary)" }}>
                Locking a baseline freezes the current schedule&rsquo;s planned duration and dates as the plan — EVM
                metrics are measured against it from that point on. Import a scheduled .xer first if you haven&rsquo;t.
              </p>
              <div className="form-row" style={{ alignItems: "flex-end" }}>
                <div className="field">
                  <label htmlFor="version-label">Version label</label>
                  <input id="version-label" type="text" value={versionLabel} onChange={(e) => setVersionLabel(e.target.value)} />
                </div>
                <button className="btn btn-primary" onClick={lockBaseline} disabled={locking}>
                  <LockIcon className="icon" /> {locking ? "Locking…" : "Lock Baseline"}
                </button>
              </div>
              {lockError && <p className="login-error">{lockError}</p>}
            </div>
          </div>
        ) : (
          <>
            <div className="banner" style={{ marginBottom: "1rem", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
                <CheckIcon className="icon" style={{ color: "var(--good)" }} />
                <span style={{ fontSize: ".8125rem" }}>
                  Baseline <b>{baselineStatus.active_baseline?.version_label}</b> locked{" "}
                  {baselineStatus.active_baseline?.locked_at && new Date(baselineStatus.active_baseline.locked_at).toLocaleDateString()}
                </span>
              </div>
              <div style={{ display: "flex", gap: ".5rem" }}>
                <button className="btn btn-secondary btn-sm" onClick={exportExcel} disabled={exporting}>
                  <DownloadIcon className="icon" /> {exporting ? "Exporting…" : "Export Excel"}
                </button>
                <button className="btn btn-danger btn-sm" onClick={supersedeBaseline} disabled={superseding}>
                  {superseding ? "Superseding…" : "Supersede"}
                </button>
              </div>
            </div>
            {lockError && (
              <p className="login-error" style={{ marginBottom: "1rem" }}>
                {lockError}
              </p>
            )}

            {summary && (
              <div className="kpi-row">
                {[
                  { label: "SPI", value: summary.spi, colored: true },
                  { label: "CPI", value: summary.cpi, colored: true },
                  { label: "EV (MH)", value: summary.ev_cumulative, colored: false },
                  { label: "AC (MH)", value: summary.ac_cumulative, colored: false },
                  { label: "PV (MH)", value: summary.pv_cumulative, colored: false },
                  { label: "EAC (MH)", value: summary.eac, colored: false },
                  { label: "TCPI", value: summary.tcpi, colored: true },
                  { label: "CV (MH)", value: summary.cv, colored: false },
                ].map((kpi) => (
                  <div className="card" key={kpi.label} style={{ padding: ".9rem 1rem" }}>
                    <div style={{ fontSize: ".6875rem", color: "var(--text-muted)", letterSpacing: ".05em" }}>
                      {kpi.label}
                    </div>
                    <div
                      className="num"
                      style={{ fontSize: "1.25rem", fontWeight: 700, marginTop: ".3rem", color: kpi.colored ? indexColor(kpi.value) : "var(--text-primary)" }}
                    >
                      {fmt(kpi.value)}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div style={{ marginTop: "1rem" }}>
              <ExpandableChartCard
                title={
                  <span style={{ display: "flex", alignItems: "center" }}>
                    <TrendingUpIcon className="icon" style={{ marginRight: ".35rem" }} />
                    S-Curve
                  </span>
                }
                subtitle="Planned vs. Earned vs. Actual (cumulative manhours)"
                headerExtra={
                  <select style={selectStyle} value={granularity} onChange={(e) => setGranularity(e.target.value as Granularity)}>
                    {GRANULARITIES.map((g) => (
                      <option key={g} value={g}>
                        {g[0].toUpperCase() + g.slice(1)}
                      </option>
                    ))}
                  </select>
                }
              >
                {scurve && scurve.series.length > 0 ? (
                  <ScurveChart series={scurve.series} />
                ) : (
                  <p className="empty-state">No progress entries yet — submit progress from the Progress Input page.</p>
                )}
              </ExpandableChartCard>
            </div>

            {baselineStatus.all_baselines.filter((b) => b.status !== "active").length > 0 && (
              <div className="card" style={{ marginTop: "1rem" }}>
                <div className="card-head">
                  <div className="card-title">Baseline History</div>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Version</th>
                        <th>Status</th>
                        <th>BAC (MH)</th>
                        <th>Locked</th>
                      </tr>
                    </thead>
                    <tbody>
                      {baselineStatus.all_baselines
                        .filter((b) => b.status !== "active")
                        .map((b) => (
                          <tr key={b.id}>
                            <td>{b.version_label}</td>
                            <td>
                              <span className="chip chip-neutral">{b.status}</span>
                            </td>
                            <td className="num">{b.total_budget_manhours.toFixed(1)}</td>
                            <td>{b.locked_at ? new Date(b.locked_at).toLocaleDateString() : "—"}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

