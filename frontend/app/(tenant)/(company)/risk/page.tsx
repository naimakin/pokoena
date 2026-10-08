"use client";

// Risk > QSRA & Finish Forecast. Runs the register-driven Monte Carlo
// (backend services/risk_analysis.py) and explains what it found: the credible
// earliest / latest finish, what drives the spread, and what to do about it.
// The old flat ±% simulation this page used to run still backs the Reporting
// block; this page no longer calls it.

import Link from "next/link";
import { PageState } from "@/components/PageShell";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { useToast } from "@/components/Toast";
import type { QsraRun, QsraRunSummary, QsraSettings } from "@/lib/types";
import { DiceIcon, SettingsIcon } from "@/components/icons";
import { CdfChart, fmtDate, fmtNum, HBarList, HistogramChart } from "@/components/risk/RiskCharts";
import { RecommendationList } from "@/components/risk/RecommendationList";
import { TrendLine } from "@/components/charts/TrendLine";

function signedDays(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (Math.abs(n) < 0.05) return "±0 d";
  return `${n > 0 ? "+" : "−"}${fmtNum(Math.abs(n), Math.abs(n) < 10 ? 1 : 0)} d`;
}

export default function QsraPage() {
  const { project, loading: loadingProject } = useProjectContext();
  const { showToast } = useToast();
  const [settings, setSettings] = useState<QsraSettings | null>(null);
  const [draft, setDraft] = useState<Partial<QsraSettings>>({});
  const [run, setRun] = useState<QsraRun | null>(null);
  const [history, setHistory] = useState<QsraRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [ranking, setRanking] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [view, setView] = useState<"pre" | "post">("pre");
  const [onlyHidden, setOnlyHidden] = useState(false);

  const load = useCallback(async () => {
    if (!project) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [s, latest, runs] = await Promise.all([
        api.get<QsraSettings>(`/projects/${project.id}/risk/qsra/settings`),
        api.get<QsraRun | null>(`/projects/${project.id}/risk/qsra/runs/latest`),
        api.get<QsraRunSummary[]>(`/projects/${project.id}/risk/qsra/runs`),
      ]);
      setSettings(s);
      setDraft({});
      setRun(latest);
      setHistory(runs);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the risk analysis.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  async function runQsra() {
    if (!project) return;
    setRunning(true);
    try {
      const res = await api.post<QsraRun>(`/projects/${project.id}/risk/qsra/runs`);
      setRun(res);
      setView("pre");
      setHistory(await api.get<QsraRunSummary[]>(`/projects/${project.id}/risk/qsra/runs`));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "The simulation failed.", "error");
    } finally {
      setRunning(false);
    }
  }

  async function runRanking() {
    if (!project || !run) return;
    setRanking(true);
    try {
      setRun(await api.post<QsraRun>(`/projects/${project.id}/risk/qsra/runs/${run.id}/ranking`));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Ranking failed.", "error");
    } finally {
      setRanking(false);
    }
  }

  async function saveSettings() {
    if (!project) return;
    try {
      const body: Record<string, unknown> = { ...draft };
      if ("target_date" in draft && !draft.target_date) body.target_date = null;
      const s = await api.put<QsraSettings>(`/projects/${project.id}/risk/qsra/settings`, body);
      setSettings({ ...s, baseline_finish: settings?.baseline_finish });
      setDraft({});
      showToast("Settings saved — run QSRA again to apply them.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save the settings.", "error");
    }
  }

  const res = run?.results ?? null;
  const dist = res ? (view === "post" && res.post ? res.post : res.pre) : null;

  const cdfSeries = useMemo(() => {
    if (!res) return [];
    const s = [{ key: "pre", label: "Pre-mitigation", color: "var(--accent)", points: res.pre.cdf }];
    if (res.post) s.push({ key: "post", label: "Post-mitigation", color: "var(--status-active)", points: res.post.cdf });
    return s;
  }, [res]);

  const markers = useMemo(() => {
    if (!res || !dist) return [];
    const m = [
      { date: res.cpm_finish, label: "CPM", tone: "ink" as const },
      { date: dist.p50, label: "P50", tone: "muted" as const },
      { date: dist.p80, label: "P80", tone: "muted" as const },
    ];
    if (res.target_date) m.push({ date: res.target_date, label: "Target", tone: "ink" as const });
    return m;
  }, [res, dist]);

  const actRows = useMemo(
    () => (res ? res.activities.filter((a) => !onlyHidden || (a.criticality_pct >= 40 && !a.p6_critical)) : []),
    [res, onlyHidden],
  );

  if (loadingProject || loading) {
    return <PageState kind="loading" section="Risk" title="QSRA & Forecast" />;
  }
  if (error) {
    return <PageState kind="error" section="Risk" title="QSRA & Forecast" message={error} />;
  }

  const s = { ...settings, ...draft } as QsraSettings;
  const dirty = Object.keys(draft).length > 0;
  const mc = res?.model_check;

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
            <div className="page-title">QSRA &amp; Forecast</div>
            <div className="page-desc">
              Monte Carlo on the live logic network with the risks in the register — the credible earliest and
              latest finish, what drives the spread, and where to act.
              {run && (
                <>
                  {" "}Last run {fmtDate(run.created_at)} on {run.revision_label ?? "the current schedule"} ·{" "}
                  {fmtNum(run.iterations)} iterations · {(run.duration_ms / 1000).toFixed(1)} s
                </>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
            <button className="btn btn-secondary" onClick={() => setSettingsOpen((v) => !v)}>
              <SettingsIcon className="icon" /> Settings
            </button>
            <button className="btn btn-primary" onClick={runQsra} disabled={running || !project}>
              <DiceIcon className="icon" /> {running ? "Simulating…" : "Run QSRA"}
            </button>
          </div>
        </div>

        {settingsOpen && settings && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Simulation settings</div>
                <div className="card-title-sub">Apply to the next run. The seed is fixed, so reruns are comparable.</div>
              </div>
            </div>
            <div className="risk-settings">
              <label>
                Schedule confidence
                <select value={s.confidence} onChange={(e) => setDraft({ ...draft, confidence: e.target.value as QsraSettings["confidence"] })}>
                  {settings.confidence_options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label} ({o.range.map((x) => x.toFixed(2)).join(" / ")})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Target finish
                <input
                  type="date"
                  value={s.target_date ?? ""}
                  onChange={(e) => setDraft({ ...draft, target_date: e.target.value || null })}
                />
                <span style={{ fontWeight: 400 }}>
                  {settings.baseline_finish ? `Empty = baseline finish ${fmtDate(settings.baseline_finish)}` : "Empty = none"}
                </span>
              </label>
              <label>
                Measure milestone (activity ID)
                <input
                  className="mono"
                  placeholder="Project finish"
                  value={s.finish_activity_external_id ?? ""}
                  onChange={(e) => setDraft({ ...draft, finish_activity_external_id: e.target.value })}
                />
              </label>
              <label>
                Iterations
                <input type="number" min={200} max={5000} step={100} value={s.iterations}
                       onChange={(e) => setDraft({ ...draft, iterations: Number(e.target.value) })} />
              </label>
              <label>
                Near-critical (working days)
                <input type="number" min={0} max={100} value={s.near_critical_days}
                       onChange={(e) => setDraft({ ...draft, near_critical_days: Number(e.target.value) })} />
              </label>
              <label className="checkbox-row" style={{ flexDirection: "row", alignItems: "center" }}>
                <input type="checkbox" checked={s.correlate_by_wbs}
                       onChange={(e) => setDraft({ ...draft, correlate_by_wbs: e.target.checked })} />
                Correlate within WBS areas
              </label>
              <button className="btn btn-primary btn-sm" disabled={!dirty} onClick={saveSettings}>Save settings</button>
            </div>
          </div>
        )}

        {!run || !res || !dist ? (
          <div className="card" style={{ padding: "1.25rem 1.1rem" }}>
            <div className="subname" style={{ marginBottom: ".4rem" }}>No simulation yet</div>
            <ol style={{ fontSize: ".8125rem", color: "var(--text-secondary)", paddingLeft: "1.1rem", lineHeight: 1.7 }}>
              <li>
                In the <Link href="/risk/register">Risk Register</Link>, open a risk, tick <b>Include in QSRA</b>,
                enter its probability and impact range, and link the activities it affects.
              </li>
              <li>Set the target finish and schedule confidence under Settings (optional).</li>
              <li>Run QSRA. Background uncertainty alone already shows how credible the CPM date is.</li>
            </ol>
          </div>
        ) : (
          <>
            <div className="card">
              <div className="risk-check">
                <span className={`chip ${mc!.calibration_ok ? "chip-good" : "chip-warn"}`}>
                  {mc!.calibration_ok ? "Model reproduces the CPM finish" : `Calibration off by ${signedDays(mc!.calibration_delta_days)}`}
                </span>
                <span className="chip chip-neutral">{fmtNum(mc!.uncertain_activities)} activities ranged</span>
                <span className="chip chip-neutral">{res.drivers.length} quantified risks</span>
                <span className="chip chip-neutral">Confidence: {res.confidence}</span>
                {mc!.hard_constraint_count > 0 && (
                  <span className="chip chip-warn">{mc!.hard_constraint_count} mandatory constraints</span>
                )}
                {mc!.iterations_capped && <span className="chip chip-info">Iterations capped for network size</span>}
                {res.measured && <span className="chip chip-info">Measuring {res.measured.external_id}</span>}
              </div>
              {(mc!.warnings.length > 0 || mc!.no_effect.length > 0) && (
                <div style={{ padding: "0 1.1rem .8rem", fontSize: ".75rem", color: "var(--text-secondary)" }}>
                  {mc!.warnings.map((w) => <div key={w}>{w}</div>)}
                  {mc!.no_effect.map((n) => (
                    <div key={n.code}>{n.code} — {n.title}: left out ({n.reason.toLowerCase()}).</div>
                  ))}
                </div>
              )}
            </div>

            {res.post && (
              <div className="segmented" style={{ alignSelf: "flex-start" }}>
                <button className={view === "pre" ? "active" : ""} onClick={() => setView("pre")}>Pre-mitigation</button>
                <button className={view === "post" ? "active" : ""} onClick={() => setView("post")}>Post-mitigation</button>
              </div>
            )}

            <div className="risk-kpis">
              {[
                { label: "CPM finish", value: res.cpm_finish, sub: "Deterministic, no risk" },
                { label: "Earliest credible (P10)", value: dist.p10, sub: signedDays(dist.p10_days) },
                { label: "Likely (P50)", value: dist.p50, sub: signedDays(dist.p50_days) },
                { label: "Commit at (P80)", value: dist.p80, sub: signedDays(dist.p80_days) },
                { label: "Latest credible (P90)", value: dist.p90, sub: signedDays(dist.p90_days) },
              ].map((k) => (
                <div className="card kpi" key={k.label}>
                  <div className="kpi-label">{k.label}</div>
                  <div className="kpi-value">{fmtDate(k.value)}</div>
                  <div className="kpi-sub">{k.sub === "Deterministic, no risk" ? k.sub : `${k.sub} vs CPM`}</div>
                </div>
              ))}
              <div className="card kpi">
                <div className="kpi-label">Chance of meeting {res.target_date ? "target" : "CPM date"}</div>
                <div className="kpi-value">
                  {fmtNum(res.target_date ? dist.prob_meet_target : dist.prob_meet_cpm)}%
                </div>
                <div className="kpi-sub">
                  {res.target_date ? `Target ${fmtDate(res.target_date)}` : `CPM ${fmtNum(dist.prob_meet_cpm)}%`}
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">Probability of finishing by date</div>
                  <div className="card-title-sub">
                    Plan at P50, commit at P80. The CPM date is optimistic wherever parallel paths converge (merge bias).
                  </div>
                </div>
              </div>
              <CdfChart series={cdfSeries} markers={markers} />
              <HistogramChart bins={dist.histogram} bin={dist.bin} />
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Percentile</th><th>Finish</th><th>vs CPM</th></tr>
                  </thead>
                  <tbody>
                    {(["p10", "p50", "p80", "p90"] as const).map((p) => (
                      <tr key={p}>
                        <td>{p.toUpperCase()}</td>
                        <td className="num">{fmtDate(dist[p])}</td>
                        <td className="num">{signedDays(dist[`${p}_days` as "p10_days"])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">From the CPM date to P80</div>
                  <div className="card-title-sub">
                    Working days each layer adds at P80. Risk exposure {signedDays(res.risk_exposure_p80_days)}
                    {res.mitigation_benefit_p80_days !== null && ` · mitigation recovers ${fmtNum(res.mitigation_benefit_p80_days, 1)} d`}
                  </div>
                </div>
              </div>
              <HBarList
                rows={res.waterfall.map((w) => ({
                  key: w.label,
                  label: w.label,
                  sub: fmtDate(w.date),
                  value: w.delta_days,
                  display: w.label === "CPM finish" ? "—" : signedDays(w.delta_days),
                }))}
                unit="working days"
              />
            </div>

            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">What drives the risk</div>
                  <div className="card-title-sub">
                    {run.ranking
                      ? `Change in P80 when each risk is switched off (${run.results.ranking_meta?.iterations ?? ""} iterations each). Contributions don't add up — risks interact through the network.`
                      : "Screening: expected delay = probability × how much later the finish is when the risk hits."}
                  </div>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={runRanking} disabled={ranking || res.drivers.length === 0}>
                  {ranking ? "Ranking…" : run.ranking ? "Re-rank" : "Run full risk ranking"}
                </button>
              </div>
              {res.drivers.length === 0 ? (
                <p className="empty-state" style={{ padding: "1rem 1.1rem" }}>
                  No quantified risks — the spread above is background uncertainty only.{" "}
                  <Link href="/risk/register">Quantify risks in the register</Link>.
                </p>
              ) : (
                <>
                  <HBarList
                    rows={
                      run.ranking
                        ? run.ranking.map((r) => ({
                            key: r.code, label: `${r.code} ${r.title}`,
                            sub: r.share_pct !== null ? `${fmtNum(r.share_pct)}% of exposure` : undefined,
                            value: r.delta_p80_days, display: signedDays(r.delta_p80_days),
                          }))
                        : res.drivers.map((d) => ({
                            key: d.code, label: `${d.code} ${d.title}`,
                            sub: `${fmtNum(d.probability_pct)}% · ${d.kind}`,
                            value: d.expected_delay_days, display: signedDays(d.expected_delay_days),
                          }))
                    }
                    unit="working days"
                  />
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Risk</th><th>Probability</th><th>Impact (min / ML / max)</th><th>Hit in runs</th>
                          <th>Delay when it hits</th><th>Expected delay</th><th>Drove the finish</th><th>Mitigation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {res.drivers.map((d) => (
                          <tr key={d.code}>
                            <td>
                              <div className="subname">{d.code} {d.title}</div>
                              <div className="actid">{d.owner ?? "No owner"} · {d.activity_count} activities</div>
                            </td>
                            <td className="num">
                              {fmtNum(d.probability_pct)}%
                              {d.probability_derived && <div className="actid">from score</div>}
                            </td>
                            <td className="num">
                              {d.impact.map((x) => fmtNum(x, 1)).join(" / ")} {d.mode === "duration_pct" ? "%" : "d"}
                            </td>
                            <td className="num">{fmtNum(d.occurred_pct)}%</td>
                            <td className="num">{signedDays(d.delay_when_occurs_days)}</td>
                            <td className="num">{signedDays(d.expected_delay_days)}</td>
                            <td className="num">{fmtNum(d.critical_hit_pct)}%</td>
                            <td><span className="chip chip-neutral">{d.mitigation_status.replace("_", " ")}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>

            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">Activity sensitivity</div>
                  <div className="card-title-sub">
                    Criticality = share of runs on the driving path. SSI = criticality × duration spread ÷ finish spread —
                    where recovery effort moves the finish most.
                  </div>
                </div>
                <label className="checkbox-row">
                  <input type="checkbox" checked={onlyHidden} onChange={(e) => setOnlyHidden(e.target.checked)} />
                  Critical in simulation, not in P6
                </label>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Activity</th><th>Criticality</th><th>SSI</th><th>Cruciality</th><th>Spread (σ)</th>
                      <th>Total float</th><th>P6</th>
                    </tr>
                  </thead>
                  <tbody>
                    {actRows.length === 0 ? (
                      <tr><td colSpan={7} className="empty-state">Nothing to show.</td></tr>
                    ) : (
                      actRows.map((a) => (
                        <tr key={a.external_id} className={a.hidden_driver ? "critical" : undefined}>
                          <td>
                            <div className="subname">{a.name}</div>
                            <div className="actid">{a.external_id}</div>
                          </td>
                          <td className="num">{fmtNum(a.criticality_pct)}%</td>
                          <td className="num">{a.ssi.toFixed(3)}</td>
                          <td className="num">{a.cruciality.toFixed(2)}</td>
                          <td className="num">{fmtNum(a.sd_days, 1)} d</td>
                          <td className="num">{a.total_float_days === null ? "—" : `${fmtNum(a.total_float_days, 1)} d`}</td>
                          <td>{a.p6_critical ? <span className="chip chip-crit">Critical</span> : <span className="chip chip-neutral">Float</span>}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">Recommendations from this run</div>
                  <div className="card-title-sub">
                    Early warnings and resource checks are added on the <Link href="/risk/mitigation-plans?tab=recommendations">Recommendations</Link> tab of Mitigation.
                  </div>
                </div>
              </div>
              <RecommendationList items={res.recommendations} empty="Nothing flagged by this run." />
            </div>
          </>
        )}

        {history.length > 0 && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Confidence across runs</div>
                <div className="card-title-sub">
                  Probability of meeting {history[history.length - 1].target_date ? "the target" : "the CPM date"} at each run
                </div>
              </div>
            </div>
            <div style={{ padding: ".6rem 1.1rem" }}>
              <TrendLine
                points={history.map((h) => ({
                  label: h.revision_label ?? fmtDate(h.created_at),
                  value: (h.target_date ? h.prob_meet_target : h.prob_meet_cpm) ?? 0,
                }))}
                color="var(--info)"
                format={(n) => `${n.toFixed(0)}%`}
              />
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Run</th><th>Update</th><th>Data date</th><th>CPM</th><th>P50</th><th>P80</th><th>P(target)</th></tr>
                </thead>
                <tbody>
                  {[...history].reverse().map((h) => (
                    <tr key={h.id}>
                      <td className="num">{fmtDate(h.created_at)}</td>
                      <td>{h.revision_label ?? "—"}</td>
                      <td className="num">{fmtDate(h.data_date)}</td>
                      <td className="num">{fmtDate(h.cpm_finish)}</td>
                      <td className="num">{fmtDate(h.p50)}</td>
                      <td className="num">{fmtDate(h.p80)}</td>
                      <td className="num">{h.prob_meet_target === null ? "—" : `${fmtNum(h.prob_meet_target)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
