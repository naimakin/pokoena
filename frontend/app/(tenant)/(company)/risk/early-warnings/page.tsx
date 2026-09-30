"use client";

// Risk > Early Warnings — the weak signals successive P6 updates leave behind
// (backend services/risk_signals.py). Nothing here needs input from anyone:
// every indicator is read from the frozen per-update snapshots, the baseline
// and the saved QSRA runs.

import { useCallback, useEffect, useState } from "react";
import { PageState } from "@/components/PageShell";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { EarlyWarningIndicator, EarlyWarnings, SignalStatus } from "@/lib/types";
import { fmtDate, Sparkline } from "@/components/risk/RiskCharts";

const STATUS: Record<SignalStatus, { chip: string; label: string }> = {
  red: { chip: "chip-crit", label: "Act now" },
  amber: { chip: "chip-warn", label: "Watch" },
  good: { chip: "chip-good", label: "On track" },
  na: { chip: "chip-neutral", label: "Not enough data" },
};

function numericSeries(ind: EarlyWarningIndicator): number[] {
  return ind.series
    .map((p) => (typeof p.value === "number" ? p.value : typeof p.value === "string" ? Date.parse(p.value) : NaN))
    .filter((v) => Number.isFinite(v));
}

function cellValue(key: string, v: string | number | boolean | null): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) return fmtDate(v);
  if (typeof v === "number") return key.endsWith("_pct") ? `${v}%` : String(v);
  return v;
}

const HEADERS: Record<string, string> = {
  external_id: "Activity ID",
  name: "Activity",
  baseline_finish: "Baseline finish",
  planned_start: "Planned start",
  forecast_finish: "Forecast finish",
  percent_complete: "% complete",
  growth_days: "Remaining grew (d)",
  critical: "Critical",
  cut_days: "Cut (d)",
  wbs: "WBS",
  density_pct: "Near-critical %",
  activities: "Activities",
  label: "Measure",
  value: "Value",
};

export default function EarlyWarningsPage() {
  const { project, loading: loadingProject } = useProjectContext();
  const [data, setData] = useState<EarlyWarnings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!project) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<EarlyWarnings>(`/projects/${project.id}/risk/early-warnings`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the early warnings.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  if (loadingProject || loading) {
    return <PageState kind="loading" section="Risk" title="Early Warnings" />;
  }
  if (error || !data) {
    return <PageState kind="error" section="Risk" title="Early Warnings" message={error ?? "No data."} />;
  }

  const selected = data.indicators.find((i) => i.id === open) ?? null;
  const counts = data.indicators.reduce(
    (acc, i) => ({ ...acc, [i.status]: (acc[i.status] ?? 0) + 1 }),
    {} as Record<string, number>,
  );

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Risk
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Early Warnings</div>
            <div className="page-desc">
              Weak signals read from {data.updates.length} schedule update{data.updates.length === 1 ? "" : "s"}
              {data.updates.length > 0 && ` (${data.updates[0].label} → ${data.updates[data.updates.length - 1].label})`} —
              the things that move before the finish date does.
              {" "}{counts.red ?? 0} to act on, {counts.amber ?? 0} to watch.
            </div>
          </div>
        </div>

        <div className="ew-grid">
          {data.indicators.map((ind) => {
            const st = STATUS[ind.status];
            const values = numericSeries(ind);
            return (
              <button
                key={ind.id}
                type="button"
                className={`card ew-card${open === ind.id ? " is-open" : ""}`}
                onClick={() => setOpen(open === ind.id ? null : ind.id)}
                aria-expanded={open === ind.id}
              >
                <div className="ew-card-head">
                  <div>
                    <div className="subname">{ind.name}</div>
                    <div className="ew-card-q">{ind.question}</div>
                  </div>
                  <span className={`chip ${st.chip}`}>{st.label}</span>
                </div>
                <div className="ew-card-value">{ind.value}</div>
                <div style={{ fontSize: ".75rem", color: "var(--text-secondary)" }}>{ind.detail}</div>
                <div className="ew-card-foot">
                  <span>Basis: {ind.basis}{ind.items.length > 0 ? ` · ${ind.items.length} item(s)` : ""}</span>
                  <Sparkline values={values} />
                </div>
              </button>
            );
          })}
        </div>

        {selected && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">{selected.name}</div>
                <div className="card-title-sub">{selected.detail}</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setOpen(null)}>Close</button>
            </div>
            {selected.series.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Update</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.series.map((p, i) => (
                      <tr key={`${p.label}-${i}`}>
                        <td>{p.label}</td>
                        <td className="num">{cellValue("value", p.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {selected.items.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {Object.keys(selected.items[0]).map((k) => (
                        <th key={k}>{HEADERS[k] ?? k}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {selected.items.map((row, i) => (
                      <tr key={i}>
                        {Object.entries(row).map(([k, v]) => (
                          <td key={k} className={k === "name" || k === "wbs" ? undefined : "num"}>
                            {cellValue(k, v)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              selected.series.length === 0 && <p className="empty-state" style={{ padding: "1rem 1.1rem" }}>Nothing to list.</p>
            )}
          </div>
        )}

        <p style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
          Thresholds marked DCMA follow the published guidance; the rest are practitioner defaults. Near-critical means
          {` ${data.near_critical_days} `}working days of float or less (set in QSRA settings).
          {data.target_date && ` Target finish ${fmtDate(data.target_date)}.`}
        </p>
      </div>
    </>
  );
}
