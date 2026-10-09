"use client";

// Risk > Resources Analysis — when does the remaining work run out at the rate
// this job has actually been earning it (backend services/risk_resources.py,
// engine/risk/resource_forecast.py)? Shown next to the logic-driven QSRA range,
// because the two answer different questions and disagree for a reason: the
// network can say "possible", production can say "not at this pace".

import { FoldPanel } from "@/components/reporting/collapse";
import { useCallback, useEffect, useState } from "react";
import { PageState } from "@/components/PageShell";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { ResourceAnalysis } from "@/lib/types";
import { fmtDate, fmtNum, WeeklyUnitsChart } from "@/components/risk/RiskCharts";

function ratioChip(r: number | null) {
  if (r === null) return <span className="chip chip-neutral">—</span>;
  if (r > 1.25) return <span className="chip chip-crit">{r.toFixed(2)}× needed</span>;
  if (r > 1.1) return <span className="chip chip-warn">{r.toFixed(2)}× needed</span>;
  return <span className="chip chip-good">{r.toFixed(2)}× needed</span>;
}

export default function ResourcesAnalysisPage() {
  const { project, loading: loadingProject } = useProjectContext();
  const [data, setData] = useState<ResourceAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rsrcType, setRsrcType] = useState<string>("");
  const [resourceId, setResourceId] = useState<string>("");

  const load = useCallback(async () => {
    if (!project) {
      setLoading(false);
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (rsrcType) qs.set("rsrc_type", rsrcType);
      if (resourceId) qs.set("resource_id", resourceId);
      setData(await api.get<ResourceAnalysis>(`/projects/${project.id}/risk/resources?${qs.toString()}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the resource analysis.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [project, rsrcType, resourceId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loadingProject || loading) {
    return <PageState kind="loading" section="Risk" title="Resources Analysis" />;
  }
  if (error || !data) {
    return <PageState kind="error" section="Risk" title="Resources Analysis" message={error ?? "No data."} />;
  }

  const tot = data.total;
  const unit = data.unit ?? "units";
  const selectable = data.resources.filter((r) => !data.rsrc_type || r.type === data.rsrc_type);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Risk
        </span>
      </div>
      <div className="a-content" style={{ opacity: refreshing ? 0.6 : 1 }}>
        <div className="page-head">
          <div>
            <div className="page-title">Resources Analysis</div>
            <div className="page-desc">
              Planned, earned and remaining work per week, and the finish range the job&apos;s demonstrated
              production supports. Data date {fmtDate(data.data_date)} · {data.updates} update
              {data.updates === 1 ? "" : "s"} of history.
            </div>
          </div>
        </div>

        <div className="filter-bar" style={{ display: "flex", gap: ".75rem", flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ display: "flex", gap: ".4rem", alignItems: "center", fontSize: ".75rem", color: "var(--text-muted)" }}>
            Resource type
            <select
              value={rsrcType || data.rsrc_type || ""}
              onChange={(e) => {
                setRsrcType(e.target.value);
                setResourceId("");
              }}
            >
              {data.types.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", gap: ".4rem", alignItems: "center", fontSize: ".75rem", color: "var(--text-muted)" }}>
            Resource
            <select value={resourceId} onChange={(e) => setResourceId(e.target.value)}>
              <option value="">All ({selectable.length})</option>
              {selectable.map((r) => (
                <option key={r.rsrc_id} value={r.rsrc_id}>{r.name}</option>
              ))}
            </select>
          </label>
        </div>

        {tot.budget === 0 ? (
          <div className="card">
            <p className="empty-state">
              No resource-loaded activities for this selection. Resource analysis needs P6 resource assignments in the
              imported schedule.
            </p>
          </div>
        ) : (
          <>
            <div className="risk-kpis">
              <div className="card kpi">
                <div className="kpi-label">Earliest credible (P10)</div>
                <div className="kpi-value">{fmtDate(tot.finish_p10)}</div>
                <div className="kpi-sub">{tot.capped ? "Capped at best rate seen + 15%" : "At the best sustained rate"}</div>
              </div>
              <div className="card kpi">
                <div className="kpi-label">Likely (P50)</div>
                <div className="kpi-value">{fmtDate(tot.finish_p50)}</div>
                <div className="kpi-sub">At the demonstrated rate</div>
              </div>
              <div className="card kpi">
                <div className="kpi-label">Latest credible (P90)</div>
                <div className="kpi-value">{fmtDate(tot.finish_p90)}</div>
                <div className="kpi-sub">If the slow periods persist</div>
              </div>
              <div className="card kpi">
                <div className="kpi-label">Work left</div>
                <div className="kpi-value">{fmtNum(tot.work_left)}</div>
                <div className="kpi-sub">{unit} of {fmtNum(tot.budget)} budget</div>
              </div>
              <div className="card kpi">
                <div className="kpi-label">Demonstrated rate</div>
                <div className="kpi-value">{fmtNum(tot.demonstrated_rate)}</div>
                <div className="kpi-sub">{unit}/week earned, recent updates weighted</div>
              </div>
              <div className="card kpi">
                <div className="kpi-label">Required rate</div>
                <div className="kpi-value">{fmtNum(tot.required_rate)}</div>
                <div className="kpi-sub">
                  {data.target_date ? `${unit}/week to finish by ${fmtDate(data.target_date)}` : "Set a target finish"}
                </div>
              </div>
            </div>

            {tot.notes.length > 0 && (
              <div className="banner">
                <div className="banner-text">{tot.notes.join(" ")}</div>
              </div>
            )}

            <FoldPanel
              title="Two forecasts, two questions"
              sub={<>The network (QSRA) asks what logic and risks allow; production asks what the pace of work supports.
                    When production is later, the plan needs more crews, not just better logic.</>}
            >
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Forecast</th><th>Earliest (P10)</th><th>Likely (P50)</th><th>Latest (P90)</th></tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Resources — demonstrated production</td>
                      <td className="num">{fmtDate(tot.finish_p10)}</td>
                      <td className="num">{fmtDate(tot.finish_p50)}</td>
                      <td className="num">{fmtDate(tot.finish_p90)}</td>
                    </tr>
                    <tr>
                      <td>
                        Network — QSRA with current risks
                        {!data.qsra && (
                          <div className="actid"><Link href="/risk">Run QSRA</Link> to compare</div>
                        )}
                      </td>
                      <td className="num">{fmtDate(data.qsra?.p10)}</td>
                      <td className="num">{fmtDate(data.qsra?.p50)}</td>
                      <td className="num">{fmtDate(data.qsra?.p90)}</td>
                    </tr>
                    <tr>
                      <td>CPM (deterministic)</td>
                      <td className="num" colSpan={3}>{fmtDate(data.qsra?.cpm_finish)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </FoldPanel>

            <FoldPanel
              title="Units per week"
              sub={<>Planned from the baseline dates; earned is budget × physical % between updates, spread evenly over
                    each update period; remaining is P6&apos;s remaining units over the current forecast dates.</>}
            >
              <WeeklyUnitsChart weeks={data.weeks} dataDate={data.data_date} unit={unit} />
            </FoldPanel>

            <FoldPanel
              title="Production between updates"
              sub={<>Productivity = earned ÷ actual units in the period (needs assignment history —{" "}
                    {data.snapshots_with_actuals} of {data.updates} updates carry it).</>}
            >
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Update</th><th>Period</th><th>Weeks</th><th>Earned</th><th>Actual</th><th>Rate / week</th><th>Productivity</th></tr>
                  </thead>
                  <tbody>
                    {data.periods.length === 0 ? (
                      <tr><td colSpan={7} className="empty-state">Needs at least two schedule updates.</td></tr>
                    ) : (
                      data.periods.map((p) => (
                        <tr key={`${p.label}-${p.end}`}>
                          <td>{p.label}</td>
                          <td className="num">{fmtDate(p.start)} – {fmtDate(p.end)}</td>
                          <td className="num">{fmtNum(p.weeks, 1)}</td>
                          <td className="num">{fmtNum(p.earned)}</td>
                          <td className="num">{fmtNum(p.actual)}</td>
                          <td className="num">{fmtNum(p.rate)}</td>
                          <td className="num">{p.productivity === null ? "—" : p.productivity.toFixed(2)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </FoldPanel>

            <FoldPanel
              title="By resource"
              sub={<>Largest budgets first. Required ÷ demonstrated above 1.10 means the plan needs a productivity jump.</>}
            >
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Resource</th><th>Budget</th><th>Earned</th><th>Actual</th><th>Work left</th>
                      <th>Productivity</th><th>Rate / week</th><th>Required vs rate</th>
                      <th>P10</th><th>P50</th><th>P90</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.per_resource.map((r) => (
                      <tr key={r.rsrc_id}>
                        <td>
                          <div className="subname">{r.name}</div>
                          <div className="actid">{r.type}{r.unit ? ` · ${r.unit}` : ""}</div>
                        </td>
                        <td className="num">{fmtNum(r.budget)}</td>
                        <td className="num">{fmtNum(r.earned)}</td>
                        <td className="num">{fmtNum(r.actual)}</td>
                        <td className="num">{fmtNum(r.work_left)}</td>
                        <td className="num">{r.cumulative_productivity === null ? "—" : r.cumulative_productivity.toFixed(2)}</td>
                        <td className="num">{fmtNum(r.demonstrated_rate)}</td>
                        <td>{ratioChip(r.rate_ratio)}</td>
                        <td className="num">{fmtDate(r.finish_p10)}</td>
                        <td className="num">{fmtDate(r.finish_p50)}</td>
                        <td className="num">{fmtDate(r.finish_p90)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </FoldPanel>
          </>
        )}
      </div>
    </>
  );
}
