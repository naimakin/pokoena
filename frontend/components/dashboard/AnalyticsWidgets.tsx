"use client";

// Dashboard / Project Status analytics blocks — GET /dashboard/analytics
// (backend/app/services/analytics.py): the KPI strip, the hours / cost gauges,
// time vs work, monthly bars, hours by WBS or activity code, budget vs actual
// and the behind-plan table. Each block takes the one analytics payload.

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import type { AnalyticsMeasure, ProjectAnalytics } from "@/lib/types";
import { fmtNum, fmtP6Date } from "@/components/reporting/format";
import { CheckIcon, ChevronRightIcon } from "@/components/icons";
import { HelpTip } from "@/components/HelpTip";
import type { HelpKey } from "@/lib/help";
import { Gauge } from "@/components/charts/Gauge";
import { TimeWorkRings } from "@/components/charts/Rings";
import { PairedBars, type BarRow } from "@/components/charts/PairedBars";
import { ComboBars, type ComboMonth } from "@/components/charts/ComboBars";
import { Sparkarea } from "@/components/charts/Sparkarea";
import { fmtCompact, fmtHours, fmtMoney, fmtPts, pctOf, ratioTone } from "@/components/charts/viz";

export type AnalyticsStatus = "idle" | "loading" | "ready" | "locked" | "error";

type Mode = "hours" | "cost";

/** Planned and actual % of budget for a measure — actual against the current
 *  budget (P6's units %), planned against the baseline's. */
export function measurePcts(m: AnalyticsMeasure): { planned: number | null; actual: number | null } {
  return {
    planned: pctOf(m.planned, m.budget),
    actual: pctOf(m.actual, m.current_budget || m.budget),
  };
}

function ModeToggle({ mode, onChange, hasCost }: { mode: Mode; onChange: (m: Mode) => void; hasCost: boolean }) {
  if (!hasCost) return null;
  return (
    <div className="segmented viz-toggle" role="group" aria-label="Measure">
      <button type="button" className={mode === "hours" ? "active" : ""} onClick={() => onChange("hours")}>
        Hours
      </button>
      <button type="button" className={mode === "cost" ? "active" : ""} onClick={() => onChange("cost")}>
        Cost
      </button>
    </div>
  );
}

export function AnalyticsState({ status, what }: { status: AnalyticsStatus; what: string }) {
  if (status === "locked") return <p className="viz-empty">Lock a baseline to see {what}.</p>;
  if (status === "error") return <p className="viz-empty">{what[0].toUpperCase() + what.slice(1)} unavailable.</p>;
  return <p className="viz-empty">Loading {what}…</p>;
}

// --- KPI strip -----------------------------------------------------------------

function spiTone(spi: number | null): "good" | "warn" | "crit" | "neutral" {
  if (spi == null) return "neutral";
  if (spi >= 0.95) return "good";
  if (spi >= 0.85) return "warn";
  return "crit";
}

function spiNote(spi: number | null): string {
  if (spi == null) return "Not enough data";
  if (spi >= 1.05) return "Ahead of plan";
  if (spi >= 0.95) return "On plan";
  return "Behind plan";
}

function KpiCell({
  label,
  value,
  sub,
  tone,
  late,
  lead,
  help,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: string;
  late?: boolean;
  lead?: ReactNode;
  help?: HelpKey;
}) {
  return (
    <div className={`viz-kpi${late ? " is-late" : ""}`}>
      <span className="viz-kpi-label">
        {lead}
        {label}
        {help && <HelpTip id={help} />}
      </span>
      <span className={`viz-kpi-value num${tone && tone !== "neutral" ? ` tone-${tone}` : ""}`}>{value}</span>
      {sub && <span className="viz-kpi-sub">{sub}</span>}
    </div>
  );
}

export function KpiStrip({ a }: { a: ProjectAnalytics }) {
  const delay = a.finish_variance_days;
  return (
    <section className="card viz-kpi-strip" aria-label="Schedule at a glance">
      <KpiCell label="Baseline start" value={fmtP6Date(a.baseline_start)} sub={a.baseline_label} />
      <KpiCell label="Baseline finish" value={fmtP6Date(a.baseline_finish)} sub="Contract target" />
      <KpiCell label="Forecast finish" value={fmtP6Date(a.forecast_finish)} sub="Current schedule" />
      <KpiCell
        label="Delay"
        help="dash.kpi-delay"
        late={delay != null && delay > 0}
        tone={delay == null ? undefined : delay > 0 ? "crit" : "good"}
        value={
          delay == null
            ? "—"
            : delay > 0
              ? `+${fmtNum(delay, 0)} ${delay === 1 ? "day" : "days"}`
              : delay === 0
                ? "On time"
                : `${fmtNum(-delay, 0)} ${delay === -1 ? "day" : "days"} ahead`
        }
        sub="Forecast vs baseline finish"
      />
      <KpiCell label="SPI" help="dash.kpi-spi" value={fmtNum(a.spi)} tone={spiTone(a.spi)} sub={spiNote(a.spi)} />
      <KpiCell
        label="Data date"
        value={fmtP6Date(a.data_date)}
        sub={a.elapsed_pct != null ? `${Math.round(a.elapsed_pct)}% of baseline span elapsed` : undefined}
        lead={<i className="dash-swatch is-datadate" aria-hidden="true" />}
      />
    </section>
  );
}

// --- gauges --------------------------------------------------------------------

export function HoursGauge({ a }: { a: ProjectAnalytics }) {
  const h = a.hours;
  const { planned, actual } = measurePcts(h);
  const has = h.budget > 0 || h.current_budget > 0;
  return (
    <Gauge
      label="Labor hours, actual vs planned"
      series="actual"
      actual={has ? actual : null}
      planned={has ? planned : null}
      emptyText="No labor resources in this schedule"
      amounts={{
        done: fmtHours(h.actual),
        planned: fmtHours(h.planned),
        rest: fmtHours(Math.max((h.current_budget || h.budget) - h.actual, 0)),
        total: fmtHours(h.current_budget || h.budget),
      }}
      caption={
        <>
          Actual <b className="num">{fmtCompact(h.actual)}</b> of {fmtHours(h.current_budget || h.budget)}
        </>
      }
    />
  );
}

export function CostGauge({ a }: { a: ProjectAnalytics }) {
  const c = a.cost;
  const { planned, actual } = c ? measurePcts(c) : { planned: null, actual: null };
  return (
    <Gauge
      label="Cost, actual vs planned"
      series="cost"
      actual={c ? actual : null}
      planned={c ? planned : null}
      emptyText="No cost loaded in this schedule"
      amounts={
        c
          ? {
              done: fmtMoney(c.actual, a.currency),
              planned: fmtMoney(c.planned, a.currency),
              rest: fmtMoney(Math.max((c.current_budget || c.budget) - c.actual, 0), a.currency),
              total: fmtMoney(c.current_budget || c.budget, a.currency),
            }
          : undefined
      }
      caption={
        c && (
          <>
            Spent <b className="num">{fmtMoney(c.actual, a.currency)}</b> of {fmtMoney(c.current_budget || c.budget, a.currency)}
          </>
        )
      }
    />
  );
}

export function TimeVsWork({ a }: { a: ProjectAnalytics }) {
  return (
    <TimeWorkRings
      elapsed={a.elapsed_pct}
      done={a.actual_pct}
      elapsedNote={dayOfSpan(a)}
      footnote={`Baseline ${fmtP6Date(a.baseline_start)} → ${fmtP6Date(a.baseline_finish)} · data date ${fmtP6Date(a.data_date)}`}
    />
  );
}

/** "day 360 of 480" — the baseline span in calendar days at the data date. */
function dayOfSpan(a: ProjectAnalytics): string | undefined {
  if (!a.baseline_start || !a.baseline_finish) return undefined;
  const day = 86_400_000;
  const start = Date.parse(a.baseline_start);
  const span = Math.round((Date.parse(a.baseline_finish) - start) / day) + 1;
  const elapsed = Math.min(Math.max(Math.round((Date.parse(a.data_date) - start) / day), 0), span);
  return `day ${fmtNum(elapsed, 0)} of ${fmtNum(span, 0)}`;
}

// --- monthly -------------------------------------------------------------------

function comboMonths(a: ProjectAnalytics, mode: Mode): ComboMonth[] {
  return a.months.map((m) => ({
    month: m.month,
    planned: mode === "hours" ? m.planned_hours : m.planned_cost,
    actual: mode === "hours" ? m.actual_hours : m.actual_cost,
  }));
}

export function MonthlyCard({ a }: { a: ProjectAnalytics }) {
  const [mode, setMode] = useState<Mode>("hours");
  const m: Mode = a.cost ? mode : "hours";
  const measure = m === "hours" ? a.hours : a.cost!;
  const months = useMemo(() => comboMonths(a, m), [a, m]);
  const series = m === "hours" ? "actual" : "cost";
  if (months.length === 0) {
    return <p className="viz-empty">No dated hours to spread by month.</p>;
  }
  return (
    <div className="viz-card-body">
      <div className="viz-card-bar">
        <div className="dash-legend">
          <span>
            <i className="viz-key is-block is-planned" aria-hidden="true" />
            Planned (baseline)
          </span>
          <span>
            <i className={`viz-key is-block is-${series}`} aria-hidden="true" />
            Actual
          </span>
          <span>
            <i className="dash-swatch is-planned" aria-hidden="true" />
            Cumulative planned
          </span>
          <span>
            <i className={`viz-key is-line is-${series}`} aria-hidden="true" />
            Cumulative actual
          </span>
          <span>
            <i className="dash-swatch is-datadate" aria-hidden="true" />
            Data date
          </span>
        </div>
        <ModeToggle mode={m} onChange={setMode} hasCost={Boolean(a.cost)} />
      </div>
      <ComboBars
        months={months}
        budget={measure.budget || measure.current_budget}
        dataDate={a.data_date}
        series={series}
        format={(v) => (m === "hours" ? `${fmtNum(v, 0)} h` : fmtMoney(v, a.currency))}
        axisFormat={(v) => (m === "hours" ? fmtCompact(v) : fmtMoney(v, a.currency))}
      />
      <p className="viz-foot">
        Planned spreads each baseline activity&rsquo;s budget evenly over its baseline dates; actuals spread over the
        activity&rsquo;s actual dates (P6 stores no dated actuals).
      </p>
    </div>
  );
}

// --- by group ------------------------------------------------------------------

export function GroupBarsCard({ a }: { a: ProjectAnalytics }) {
  const [key, setKey] = useState<string>(a.groupings[0]?.key ?? "");
  const [mode, setMode] = useState<Mode>("hours");
  const [unit, setUnit] = useState<"pct" | "amount">("pct");
  const grouping = a.groupings.find((g) => g.key === key) ?? a.groupings[0];
  const m: Mode = a.cost ? mode : "hours";
  if (!grouping) {
    return <p className="viz-empty">No WBS levels or activity codes to group by.</p>;
  }
  const series = m === "hours" ? "actual" : "cost";
  // A branch with no budget in this measure (milestones, change management)
  // has nothing to compare — leave it out rather than draw an empty row.
  const measured = grouping.groups.filter((g) => {
    const measure = m === "hours" ? g.hours : g.cost;
    return measure.budget > 0 || measure.current_budget > 0;
  });
  const rows: BarRow[] = measured.map((g, i) => {
    const measure = m === "hours" ? g.hours : g.cost;
    const pcts = measurePcts(measure);
    const fmtAmt = (v: number) => (m === "hours" ? fmtHours(v) : fmtMoney(v, a.currency));
    return unit === "pct"
      ? {
          key: `${i}`,
          label: g.label,
          planned: pcts.planned,
          actual: pcts.actual,
          details: [{ label: "Budget", value: fmtAmt(measure.current_budget || measure.budget) }],
        }
      : {
          key: `${i}`,
          label: g.label,
          planned: measure.planned,
          actual: measure.actual,
          total: measure.current_budget || measure.budget,
          details: [{ label: "Budget", value: fmtAmt(measure.current_budget || measure.budget) }],
        };
  });
  const format =
    unit === "pct"
      ? (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`)
      : (v: number | null) => (v == null ? "—" : m === "hours" ? fmtHours(v) : fmtMoney(v, a.currency));

  return (
    <div className="viz-card-body">
      <div className="viz-card-bar">
        <select className="select select-sm" value={grouping.key} onChange={(e) => setKey(e.target.value)} aria-label="Group by">
          {a.groupings.map((g) => (
            <option key={g.key} value={g.key}>
              {g.label}
            </option>
          ))}
        </select>
        <div className="viz-card-tools">
          <div className="segmented viz-toggle" role="group" aria-label="Unit">
            <button type="button" className={unit === "pct" ? "active" : ""} onClick={() => setUnit("pct")}>
              %
            </button>
            <button type="button" className={unit === "amount" ? "active" : ""} onClick={() => setUnit("amount")}>
              {m === "hours" ? "Hours" : "Amount"}
            </button>
          </div>
          <ModeToggle mode={m} onChange={setMode} hasCost={Boolean(a.cost)} />
        </div>
      </div>
      <div className="dash-legend">
        <span>
          <i className="viz-key is-block is-planned" aria-hidden="true" />
          Planned to date
        </span>
        <span>
          <i className={`viz-key is-block is-${series}`} aria-hidden="true" />
          Actual
        </span>
        {unit === "amount" && (
          <span>
            <i className="viz-key is-block is-total" aria-hidden="true" />
            Budget
          </span>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="viz-empty">No {m === "hours" ? "labor hours" : "cost"} in this grouping.</p>
      ) : (
        <PairedBars rows={rows} series={series} max={unit === "pct" ? 100 : undefined} format={format} limit={10} />
      )}
    </div>
  );
}

// --- budget vs actual ----------------------------------------------------------

export function BudgetActualCard({ a }: { a: ProjectAnalytics }) {
  const [mode, setMode] = useState<Mode>("hours");
  const m: Mode = a.cost ? mode : "hours";
  const measure = m === "hours" ? a.hours : a.cost!;
  const fmt = (v: number) => (m === "hours" ? fmtHours(v) : fmtMoney(v, a.currency));
  const budget = measure.current_budget || measure.budget;
  const ofBudget = pctOf(measure.actual, budget);
  const plannedPct = pctOf(measure.planned, measure.budget);
  const tone = ratioTone(ofBudget, plannedPct);
  const months = useMemo(() => comboMonths(a, m), [a, m]);
  return (
    <div className="viz-card-body viz-bignum-card">
      <div className="viz-card-bar">
        <div className="viz-bignum">
          <span className="viz-bignum-label">Budget at completion</span>
          <span className="viz-bignum-value num">{fmt(budget)}</span>
          {measure.budget > 0 && Math.abs(measure.budget - measure.current_budget) > 0.5 && (
            <span className="viz-bignum-sub">Baseline {fmt(measure.budget)}</span>
          )}
        </div>
        <ModeToggle mode={m} onChange={setMode} hasCost={Boolean(a.cost)} />
      </div>
      <div className="viz-bignum">
        <span className="viz-bignum-label">Actual to date</span>
        <span className="viz-bignum-value is-lg num">{fmt(measure.actual)}</span>
        <span className="viz-bignum-sub">
          {ofBudget == null ? "No budget" : `${Math.round(ofBudget)}% of budget`}
          {plannedPct != null && (
            <>
              {" · "}
              <span className={tone === "warn" || tone === "crit" ? `tone-${tone}` : undefined}>
                planned {Math.round(plannedPct)}% by now
              </span>
            </>
          )}
        </span>
      </div>
      <Sparkarea
        months={months}
        dataDate={a.data_date}
        series={m === "hours" ? "actual" : "cost"}
        budget={measure.budget || budget}
        format={fmt}
      />
      <div className="dash-legend">
        <span>
          <i className="dash-swatch is-planned" aria-hidden="true" />
          Planned (cumulative)
        </span>
        <span>
          <i className={`viz-key is-line is-${m === "hours" ? "actual" : "cost"}`} aria-hidden="true" />
          Actual
        </span>
        <span>Remaining {fmt(measure.remaining)}</span>
      </div>
    </div>
  );
}

// --- behind plan ---------------------------------------------------------------

export function BehindPlanTable({ a, compact = false }: { a: ProjectAnalytics; compact?: boolean }) {
  if (a.behind.length === 0) {
    return (
      <p className="viz-empty viz-empty-good">
        <CheckIcon className="icon icon-sm" aria-hidden="true" /> No activities behind plan at this data date.
      </p>
    );
  }
  return (
    <div className="table-wrap">
      <table className="viz-behind">
        <thead>
          <tr>
            <th>Activity</th>
            <th className="num">Plan</th>
            <th className="num">Actual</th>
            <th className="num">Variance</th>
            {!compact && <th aria-label="Progress" />}
          </tr>
        </thead>
        <tbody>
          {a.behind.map((r) => {
            const tone = ratioTone(r.actual_pct, r.planned_pct);
            return (
              <tr key={r.activity_id}>
                <td>
                  <span className="viz-behind-id mono">{r.external_id}</span>
                  <span className="viz-behind-name" title={r.wbs_name ? `${r.name} · ${r.wbs_name}` : r.name}>
                    {r.name}
                  </span>
                </td>
                <td className="num">{Math.round(r.planned_pct)}%</td>
                <td className="num">{Math.round(r.actual_pct)}%</td>
                <td className={`num${tone === "crit" || tone === "warn" ? ` tone-${tone}` : ""}`}>{fmtPts(r.variance)}</td>
                {!compact && (
                  <td className="viz-behind-bullet" aria-hidden="true">
                    <span className="viz-mini">
                      <span className="viz-mini-fill" style={{ width: `${Math.min(r.actual_pct, 100)}%` }} />
                      <span className="viz-mini-tick" style={{ left: `${Math.min(r.planned_pct, 100)}%` }} />
                    </span>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {a.behind_total > a.behind.length && (
        <p className="viz-foot viz-foot-pad">
          Worst {a.behind.length} of {a.behind_total} activities more than 5 pts behind plan.
        </p>
      )}
    </div>
  );
}

export function BehindPlanLink() {
  return (
    <Link href="/activity-workspace" className="card-link">
      Activity Workspace
      <ChevronRightIcon className="icon" aria-hidden="true" />
    </Link>
  );
}
