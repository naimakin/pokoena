"use client";

// Portfolio Dashboard's visual summary: the phase donut (which also filters
// the page), the portfolio's labor hours gauge, a portfolio SPI tile, and
// "Progress by project" — one bullet row per project, built to stay legible
// from two projects to forty.

import { useMemo, useState } from "react";
import type { PortfolioProject } from "@/lib/portfolio";
import { Gauge } from "@/components/charts/Gauge";
import { StatusDonut, type DonutSegment } from "@/components/charts/Rings";
import { PairedBars, type BarRow } from "@/components/charts/PairedBars";
import { fmtCompact, fmtHours, fmtMoney, pctOf, ratioTone } from "@/components/charts/viz";
import { fmtNum } from "@/components/reporting/format";

export type Phase = "complete" | "progress" | "notstarted" | "nobaseline";

export const PHASE_LABEL: Record<Phase, string> = {
  complete: "Complete",
  progress: "In progress",
  notstarted: "Not started",
  nobaseline: "No baseline",
};

export function phaseOf(p: PortfolioProject): Phase {
  if (!p.has_schedule || !p.has_baseline) return "nobaseline";
  const actual = p.actual_pct ?? 0;
  if (actual >= 99.95) return "complete";
  if (actual > 0) return "progress";
  return "notstarted";
}

function sumMeasures(projects: PortfolioProject[], key: "hours" | "cost") {
  const t = { budget: 0, current_budget: 0, planned: 0, actual: 0, remaining: 0 };
  for (const p of projects) {
    const m = p[key];
    if (!m) continue;
    t.budget += m.budget;
    t.current_budget += m.current_budget;
    t.planned += m.planned;
    t.actual += m.actual;
    t.remaining += m.remaining;
  }
  return t;
}

function spiTone(spi: number | null): string {
  if (spi == null) return "neutral";
  if (spi >= 0.95) return "good";
  if (spi >= 0.85) return "warn";
  return "crit";
}

export function PortfolioGlance({
  projects,
  phase,
  onPhase,
}: {
  /** Every project (the donut counts all of them, whatever else is filtered). */
  projects: PortfolioProject[];
  phase: Phase | null;
  onPhase: (p: Phase | null) => void;
}) {
  const segments: DonutSegment[] = (["complete", "progress", "notstarted", "nobaseline"] as Phase[]).map((k) => ({
    key: k,
    label: PHASE_LABEL[k],
    value: projects.filter((p) => phaseOf(p) === k).length,
    tone: k,
  }));
  const measured = projects.filter((p) => p.has_baseline && p.hours);
  const hours = sumMeasures(measured, "hours");
  const plannedPct = pctOf(hours.planned, hours.budget);
  const actualPct = pctOf(hours.actual, hours.current_budget || hours.budget);
  const spi = plannedPct && actualPct != null ? actualPct / plannedPct : null;
  const behind = projects.filter((p) => p.progress === "behind" || p.progress === "slightly_behind").length;
  const scheduled = projects.filter((p) => p.has_schedule).length;

  return (
    <div className="pf-glance">
      <section className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Projects by phase</div>
            <div className="card-title-sub">Click a phase to filter the page</div>
          </div>
        </div>
        <div className="pf-glance-body">
          <StatusDonut
            segments={segments}
            centerLabel={projects.length === 1 ? "project" : "projects"}
            selected={phase}
            onSelect={(k) => onPhase(k as Phase | null)}
          />
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Portfolio labor hours</div>
            <div className="card-title-sub">
              {measured.length} of {projects.length} projects with a baseline, hours-weighted
            </div>
          </div>
        </div>
        <div className="pf-glance-body">
          <Gauge
            label="Portfolio labor hours, actual vs planned"
            series="actual"
            actual={hours.budget > 0 || hours.current_budget > 0 ? actualPct : null}
            planned={hours.budget > 0 ? plannedPct : null}
            emptyText="No labor resources in the baselined programmes"
            caption={
              <>
                Actual <b className="num">{fmtCompact(hours.actual)}</b> of {fmtHours(hours.current_budget || hours.budget)}
              </>
            }
          />
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Portfolio performance</div>
            <div className="card-title-sub">Hours-weighted across baselined projects</div>
          </div>
        </div>
        <div className="pf-glance-body pf-spi">
          <div>
            <div className="viz-bignum-label">SPI (labor hours)</div>
            <div className={`pf-spi-value num tone-${spiTone(spi)}`}>{fmtNum(spi)}</div>
          </div>
          <div className="pf-spi-row">
            <span>Planned by now</span>
            <b className="num">{plannedPct == null ? "—" : `${plannedPct.toFixed(1)}%`}</b>
          </div>
          <div className="pf-spi-row">
            <span>Actual</span>
            <b className="num">{actualPct == null ? "—" : `${actualPct.toFixed(1)}%`}</b>
          </div>
          <div className="pf-spi-row">
            <span>Behind plan</span>
            <b className={`num${behind ? " tone-warn" : ""}`}>
              {behind} of {scheduled} projects
            </b>
          </div>
        </div>
      </section>
    </div>
  );
}

type Unit = "pct" | "hours" | "cost";
type Order = "variance" | "name" | "size";

export function ProgressByProject({
  projects,
  currency,
  onOpen,
}: {
  projects: PortfolioProject[];
  currency: string;
  onOpen: (p: PortfolioProject) => void;
}) {
  const [unit, setUnit] = useState<Unit>("pct");
  const [order, setOrder] = useState<Order>("variance");
  const hasCost = projects.some((p) => p.cost);
  const u: Unit = unit === "cost" && !hasCost ? "pct" : unit;

  const rows = useMemo(() => {
    const list = projects.filter((p) => p.has_schedule);
    const out: (BarRow & { sortGap: number; size: number })[] = list.map((p) => {
      const m = u === "cost" ? p.cost : p.hours;
      const fmtAmt = (v: number) => (u === "cost" ? fmtMoney(v, currency) : fmtHours(v));
      const base = {
        key: p.id,
        label: `${p.name}`,
        onOpen: () => onOpen(p),
        size: p.hours?.current_budget || p.hours?.budget || 0,
      };
      if (u === "pct") {
        return {
          ...base,
          planned: p.planned_pct,
          actual: p.actual_pct,
          sortGap: (p.actual_pct ?? 0) - (p.planned_pct ?? 0),
          details: [
            { label: "SPI", value: fmtNum(p.spi) },
            ...(p.hours ? [{ label: "Budget", value: fmtHours(p.hours.current_budget || p.hours.budget) }] : []),
          ],
        };
      }
      return {
        ...base,
        planned: m ? m.planned : null,
        actual: m ? m.actual : null,
        total: m ? m.current_budget || m.budget : null,
        sortGap: m ? (pctOf(m.actual, m.current_budget || m.budget) ?? 0) - (pctOf(m.planned, m.budget) ?? 0) : 0,
        details: m ? [{ label: "Budget", value: fmtAmt(m.current_budget || m.budget) }] : [],
      };
    });
    out.sort((a, b) =>
      order === "name"
        ? a.label.localeCompare(b.label)
        : order === "size"
          ? b.size - a.size
          : a.sortGap - b.sortGap,
    );
    return out;
  }, [projects, u, order, currency, onOpen]);

  const behind = rows.filter((r) => ratioTone(r.actual, r.planned) === "crit").length;
  const format =
    u === "pct"
      ? (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`)
      : (v: number | null) => (v == null ? "—" : u === "cost" ? fmtMoney(v, currency) : fmtHours(v));

  return (
    <section className="card pf-card">
      <div className="card-head">
        <div>
          <div className="card-title">Progress by project</div>
          <div className="card-title-sub">
            Bar = actual, tick = planned by the data date
            {behind > 0 && ` · ${behind} well behind plan`}
          </div>
        </div>
        <div className="pf-progress-tools">
          <div className="segmented viz-toggle" role="group" aria-label="Unit">
            <button type="button" className={u === "pct" ? "active" : ""} onClick={() => setUnit("pct")}>
              Percent
            </button>
            <button type="button" className={u === "hours" ? "active" : ""} onClick={() => setUnit("hours")}>
              Hours
            </button>
            {hasCost && (
              <button type="button" className={u === "cost" ? "active" : ""} onClick={() => setUnit("cost")}>
                Cost
              </button>
            )}
          </div>
          <select value={order} onChange={(e) => setOrder(e.target.value as Order)} aria-label="Sort projects" className="pf-sort">
            <option value="variance">Worst variance first</option>
            <option value="name">Name</option>
            <option value="size">Largest first</option>
          </select>
        </div>
      </div>
      <div className="viz-card-body">
        {rows.length === 0 ? (
          <p className="viz-empty">No projects match.</p>
        ) : (
          <PairedBars
            rows={rows}
            variant="bullet"
            max={u === "pct" ? 100 : undefined}
            format={format}
            limit={12}
            showAllLabel={(n) => `Show all ${n} projects`}
          />
        )}
      </div>
    </section>
  );
}
