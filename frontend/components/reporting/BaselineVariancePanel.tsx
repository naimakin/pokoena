"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { BaselineStatus, BaselineVariance, EvmScurve } from "@/lib/types";
import { ScurveChart } from "@/components/ScurveChart";
import { ChevronDownIcon, ChevronRightIcon } from "@/components/icons";
import { fmtP6Date } from "@/components/reporting/format";

type Tone = "good" | "info" | "warn" | "crit" | "muted";

const TONE_VAR: Record<Tone, string> = {
  good: "var(--good)",
  info: "var(--info)",
  warn: "var(--warn)",
  crit: "var(--crit)",
  muted: "var(--text-primary)",
};

// Same bands as the activity chips: on time or early is good, up to 15 days
// late is a warning, beyond that critical.
function slipTone(days: number | null | undefined): Tone {
  if (days === null || days === undefined) return "muted";
  if (days <= 0) return "good";
  if (days <= 15) return "warn";
  return "crit";
}

function binTone(label: string): Tone {
  const l = label.toLowerCase();
  if (l.includes("early")) return "good";
  if (l.includes("on baseline")) return "info";
  if (l.startsWith("1-30") || l.startsWith("1–30")) return "warn";
  return "crit";
}

function signed(days: number | null | undefined): string {
  if (days === null || days === undefined) return "—";
  if (days === 0) return "0 d";
  return `${days > 0 ? "+" : ""}${days} d`;
}

function pct(part: number, whole: number): string {
  return whole > 0 ? `${Math.round((part / whole) * 100)}%` : "—";
}

/** Baseline vs current schedule: slip KPIs, the finish-variance distribution,
 *  the S-curve and the per-activity variance table. Always the whole
 *  programme — it reads the baseline endpoints, which take no filters. */
export function BaselineVariancePanel({ projectId }: { projectId: string }) {
  const [hasBaseline, setHasBaseline] = useState<boolean | null>(null);
  const [variance, setVariance] = useState<BaselineVariance | null>(null);
  const [scurve, setScurve] = useState<EvmScurve | null>(null);
  const [tableOpen, setTableOpen] = useState(false);
  const [slippingOnly, setSlippingOnly] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setHasBaseline(null);
    setVariance(null);
    setScurve(null);
    (async () => {
      try {
        const status = await api.get<BaselineStatus>(`/projects/${projectId}/evm/baseline`);
        if (cancelled) return;
        setHasBaseline(status.has_active);
        if (!status.has_active) return;
        const [v, s] = await Promise.all([
          api.get<BaselineVariance>(`/projects/${projectId}/evm/baseline/variance`),
          api.get<EvmScurve>(`/projects/${projectId}/evm/scurve?granularity=weekly`).catch(() => null),
        ]);
        if (cancelled) return;
        setVariance(v);
        setScurve(s);
      } catch {
        if (!cancelled) setHasBaseline(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const head = (sub: string) => (
    <div className="card-head" style={{ border: "none", padding: 0 }}>
      <div className="card-title" style={{ fontFamily: "var(--font-display)", fontSize: "1rem", letterSpacing: "-.01em" }}>
        Baseline vs current schedule
      </div>
      <div className="card-title-sub">{sub}</div>
    </div>
  );

  if (hasBaseline === null || (hasBaseline && !variance)) {
    return (
      <>
        {head("Loading…")}
        <div className="card">
          <p className="empty-state">Loading baseline comparison…</p>
        </div>
      </>
    );
  }
  if (!hasBaseline || !variance) {
    return (
      <>
        {head("No baseline locked")}
        <div className="card">
          <p className="empty-state">
            Lock a baseline programme in <Link href="/planning/baselines">Baselines</Link> to compare the latest update
            against it.
          </p>
        </div>
      </>
    );
  }

  const s = variance.summary;
  const total = s.activities_total;
  const slip = slipTone(s.project_finish_variance_days);
  const histMax = Math.max(...s.finish_variance_histogram.map((b) => b.count), 1);
  const histTotal = s.finish_variance_histogram.reduce((n, b) => n + b.count, 0);
  const rows = slippingOnly ? variance.rows.filter((r) => (r.finish_variance_days ?? 0) > 0) : variance.rows;

  const kpis: { label: string; value: string; tone: Tone; note: string }[] = [
    { label: "Baseline finish", value: fmtP6Date(s.baseline_finish), tone: "muted", note: `Baseline ${variance.version_label}` },
    { label: "Forecast finish", value: fmtP6Date(s.forecast_finish), tone: slip, note: "Latest update programme" },
    {
      label: "Project slip",
      value: signed(s.project_finish_variance_days),
      tone: slip,
      note: (s.project_finish_variance_days ?? 0) > 0 ? "Finish later than baseline" : "On or ahead of baseline",
    },
    { label: "Activities behind", value: s.behind.toLocaleString(), tone: s.behind > 0 ? "warn" : "good", note: `${pct(s.behind, total)} of ${total.toLocaleString()} activities` },
    { label: "Worst slip", value: signed(s.worst_slip_days), tone: slipTone(s.worst_slip_days), note: "Largest single finish slip" },
    { label: "Critical slipping", value: s.critical_slip_count.toLocaleString(), tone: s.critical_slip_count > 0 ? "crit" : "good", note: "Critical activities finishing late" },
  ];

  return (
    <>
      {head(`Baseline ${variance.version_label} · whole programme — the filters above don't apply here`)}

      <div className="bl-kpis">
        {kpis.map((k) => (
          <div key={k.label} className="card" style={{ padding: "1rem 1.1rem" }}>
            <div style={{ fontSize: ".75rem", color: "var(--text-muted)", fontWeight: 500 }}>{k.label}</div>
            <div className="num" style={{ fontSize: "1.375rem", fontWeight: 700, margin: ".35rem 0 .15rem", color: TONE_VAR[k.tone] }}>
              {k.value}
            </div>
            <div style={{ fontSize: ".6875rem", color: "var(--text-muted)" }}>{k.note}</div>
          </div>
        ))}
      </div>

      <div className="bl-split">
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Finish-date variance</div>
              <div className="card-title-sub">Current finish against baseline finish, per activity</div>
            </div>
          </div>
          <div style={{ padding: "1rem 1.1rem 1.15rem" }}>
            {/* Ahead / on baseline / behind at a glance, then the detail. */}
            <div className="bl-stack" role="img" aria-label={`${s.ahead} ahead, ${s.on_track} on baseline, ${s.behind} behind`}>
              {[
                { n: s.ahead, tone: "good" as Tone },
                { n: s.on_track, tone: "info" as Tone },
                { n: s.behind, tone: "crit" as Tone },
              ]
                .filter((x) => x.n > 0)
                .map((x, i) => (
                  <span key={i} style={{ flexGrow: x.n, background: TONE_VAR[x.tone] }} />
                ))}
            </div>
            <div className="bl-legend">
              <span><i style={{ background: "var(--good)" }} />{s.ahead.toLocaleString()} ahead</span>
              <span><i style={{ background: "var(--info)" }} />{s.on_track.toLocaleString()} on baseline</span>
              <span><i style={{ background: "var(--crit)" }} />{s.behind.toLocaleString()} behind</span>
            </div>

            <div className="bl-hist">
              {s.finish_variance_histogram.map((b) => (
                <div key={b.label} className="bl-hist-row">
                  <span className="bl-hist-label">{b.label}</span>
                  <span className="bl-hist-track">
                    <span style={{ width: `${(b.count / histMax) * 100}%`, background: TONE_VAR[binTone(b.label)] }} />
                  </span>
                  <span className="num bl-hist-count">{b.count.toLocaleString()}</span>
                  <span className="num bl-hist-share">{pct(b.count, histTotal)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">S-curve</div>
              <div className="card-title-sub">Planned vs earned vs actual, cumulative manhours</div>
            </div>
            <Link className="card-link" href="/evm">
              S-Curve &amp; EVM
              <ChevronRightIcon className="icon" />
            </Link>
          </div>
          <div style={{ padding: ".5rem 1rem 1rem" }}>
            {scurve && scurve.series.length > 0 ? (
              <ScurveChart series={scurve.series} />
            ) : (
              <p className="empty-state">No S-curve data yet.</p>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div
          className="card-head"
          role="button"
          tabIndex={0}
          aria-expanded={tableOpen}
          onClick={() => setTableOpen((o) => !o)}
          onKeyDown={(e) => {
            if (e.target !== e.currentTarget) return;
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setTableOpen((o) => !o);
            }
          }}
          style={{ cursor: "pointer", userSelect: "none", ...(tableOpen ? {} : { borderBottom: "none" }) }}
        >
          <div className="card-title cell-flex">
            <ChevronDownIcon
              className="icon"
              style={{ transform: tableOpen ? undefined : "rotate(-90deg)", transition: "transform var(--dur-1) var(--ease)" }}
            />
            Activity date variance
            <span className="card-count">{rows.length.toLocaleString()}</span>
          </div>
          <label
            style={{ display: "flex", alignItems: "center", gap: ".35rem", fontSize: ".75rem" }}
            onClick={(e) => e.stopPropagation()}
          >
            <input type="checkbox" checked={slippingOnly} onChange={(e) => setSlippingOnly(e.target.checked)} />
            Slipping only
          </label>
        </div>
        {tableOpen && (
          <div className="table-wrap" style={{ maxHeight: 480, overflowY: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Activity</th>
                  <th>Baseline finish</th>
                  <th>Current finish</th>
                  <th>Finish var</th>
                  <th>Start var</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="empty-state">
                      {slippingOnly ? "Nothing slipping against the baseline." : "No activities."}
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => {
                    const t = slipTone(r.finish_variance_days);
                    return (
                      <tr key={r.activity_id} className={r.is_critical && t === "crit" ? "critical" : undefined}>
                        <td>
                          <div className="subname">{r.name}</div>
                          <div className="actid">
                            {r.external_id}
                            {r.is_critical && (
                              <span className="chip chip-crit" style={{ marginLeft: ".35rem" }}>
                                Critical
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="num">{fmtP6Date(r.baseline_finish)}</td>
                        <td className="num">{fmtP6Date(r.current_finish)}</td>
                        <td>
                          <span className={`chip chip-${t === "muted" ? "neutral" : t}`}>{signed(r.finish_variance_days)}</span>
                        </td>
                        <td className="num">{signed(r.start_variance_days)}</td>
                        <td className="num">{r.percent_complete}%</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
