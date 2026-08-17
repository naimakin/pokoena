"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { MonteCarloResult, Project } from "@/lib/types";
import { DiceIcon } from "@/components/icons";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "2-digit", year: "numeric" });
}

export default function RiskPage() {
  const [project, setProject] = useState<Project | null>(null);
  const [loadingProject, setLoadingProject] = useState(true);
  const [projectError, setProjectError] = useState<string | null>(null);

  const [iterations, setIterations] = useState(1000);
  const [spreadPct, setSpreadPct] = useState(20);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<MonteCarloResult | null>(null);

  useEffect(() => {
    async function load() {
      setLoadingProject(true);
      setProjectError(null);
      try {
        const projects = await api.get<Project[]>("/projects");
        setProject(projects[0] ?? null);
      } catch (err) {
        setProjectError(err instanceof ApiError ? err.message : "Failed to load the project.");
      } finally {
        setLoadingProject(false);
      }
    }
    load();
  }, []);

  async function runSimulation() {
    if (!project) return;
    setRunning(true);
    setRunError(null);
    try {
      const res = await api.post<MonteCarloResult>(`/projects/${project.id}/risk/monte-carlo`, {
        iterations,
        spread: spreadPct / 100,
      });
      setResult(res);
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "Failed to run the simulation.");
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  const maxCount = result ? Math.max(...result.histogram.map((b) => b.count), 1) : 1;

  if (loadingProject) {
    return (
      <div className="a-content">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }
  if (projectError) {
    return (
      <div className="a-content">
        <p className="login-error" style={{ maxWidth: 420 }}>
          {projectError}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Risk Analysis</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Risk Analysis</div>
            <div className="page-desc">Monte Carlo schedule-risk simulation — triangular duration distribution per activity</div>
          </div>
        </div>

        {!project ? (
          <div className="card">
            <p className="empty-state">No project yet.</p>
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: "1rem 1.1rem" }}>
              <div className="form-row" style={{ alignItems: "flex-end" }}>
                <div className="field" style={{ maxWidth: 160 }}>
                  <label htmlFor="iterations">Iterations</label>
                  <input
                    id="iterations"
                    type="number"
                    min={1}
                    max={5000}
                    value={iterations}
                    onChange={(e) => setIterations(Number(e.target.value))}
                  />
                </div>
                <div className="field" style={{ maxWidth: 160 }}>
                  <label htmlFor="spread">Duration spread (±%)</label>
                  <input
                    id="spread"
                    type="number"
                    min={0}
                    max={100}
                    value={spreadPct}
                    onChange={(e) => setSpreadPct(Number(e.target.value))}
                  />
                </div>
                <button className="btn btn-primary" onClick={runSimulation} disabled={running}>
                  <DiceIcon className="icon" /> {running ? "Running…" : "Run Simulation"}
                </button>
              </div>
              {runError && (
                <p className="login-error" style={{ marginTop: ".75rem" }}>
                  {runError}
                </p>
              )}
            </div>

            {result && (
              <>
                <div className="kpi-row" style={{ marginTop: "1rem" }}>
                  {[
                    { label: "P10 Finish", value: result.project_finish_p10, sub: "Optimistic" },
                    { label: "P50 Finish", value: result.project_finish_p50, sub: "Median" },
                    { label: "P80 Finish", value: result.project_finish_p80, sub: "Likely" },
                    { label: "P90 Finish", value: result.project_finish_p90, sub: "Conservative" },
                  ].map((kpi) => (
                    <div className="card" key={kpi.label} style={{ padding: "1rem 1.1rem" }}>
                      <div style={{ fontSize: ".6875rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".05em" }}>
                        {kpi.label}
                      </div>
                      <div className="num" style={{ fontSize: "1.125rem", fontWeight: 700, marginTop: ".3rem" }}>
                        {fmtDate(kpi.value)}
                      </div>
                      <div style={{ fontSize: ".6875rem", color: "var(--text-muted)" }}>{kpi.sub}</div>
                    </div>
                  ))}
                </div>

                <div className="card" style={{ marginTop: "1rem" }}>
                  <div className="card-head">
                    <div className="card-title">Finish Date Distribution</div>
                    <div className="card-title-sub">{result.iterations} iterations</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 140, padding: "1rem 1.1rem" }}>
                    {result.histogram.map((bin, i) => (
                      <div
                        key={i}
                        title={`${bin.date}: ${bin.count} runs (${bin.cumulative_pct}% cumulative)`}
                        style={{
                          flex: 1,
                          height: `${Math.max((bin.count / maxCount) * 100, 2)}%`,
                          background: "var(--info)",
                          borderRadius: "2px 2px 0 0",
                        }}
                      />
                    ))}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "0 1.1rem .9rem", fontSize: ".6875rem", color: "var(--text-muted)" }}>
                    <span>{result.histogram[0] && fmtDate(result.histogram[0].date)}</span>
                    <span>{result.histogram.length > 0 && fmtDate(result.histogram[result.histogram.length - 1].date)}</span>
                  </div>
                </div>

                <div className="card" style={{ marginTop: "1rem" }}>
                  <div className="card-head">
                    <div className="card-title">Critical Activities</div>
                    <div className="card-title-sub">Finished within the project finish window in &gt;50% of runs</div>
                  </div>
                  <div style={{ padding: "1rem 1.1rem", display: "flex", flexWrap: "wrap", gap: ".4rem" }}>
                    {result.critical_activities.length === 0 ? (
                      <span className="empty-state">No single activity dominates the finish date across runs.</span>
                    ) : (
                      result.critical_activities.map((id) => (
                        <span key={id} className="chip chip-crit mono">
                          {id}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
