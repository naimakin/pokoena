"use client";

// What a simulation run shows: the headline (project finish, what moved,
// milestones, critical path), a slip chart of the milestones, and every moved
// activity with what drives it now and the chain back to the change.

import { Fragment, useMemo, useState } from "react";
import { AlertTriangleIcon, ArrowRightIcon, ChevronDownIcon, DownloadIcon } from "@/components/icons";
import { FloatBadge, fmtP6Date } from "@/components/reporting/format";
import {
  deltaClass,
  downloadText,
  driverText,
  linkText,
  movedCsv,
  signedDays,
  walkChain,
  type SimResult,
  type SimRow,
} from "@/lib/simulation";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const PAGE = 200;

type Filter = "all" | "later" | "earlier" | "critical";
type SortKey = "delta" | "finish" | "id";

function Delta({ days, word = true }: { days: number | null | undefined; word?: boolean }) {
  const r = Math.round((days ?? 0) * 10) / 10;
  const title = r === 0 ? "No change" : `${Math.abs(r)} working days ${r > 0 ? "later" : "earlier"}`;
  return (
    <span className={deltaClass(days)} title={title}>
      {signedDays(days)}
      {word && r !== 0 && <span className="sim-sr-only">{r > 0 ? " later" : " earlier"}</span>}
    </span>
  );
}

function BeforeAfter({ before, after }: { before: string | null; after: string | null }) {
  if (!before && !after) return <span className="sim-ba is-same">—</span>;
  if (before === after) {
    return (
      <span className="sim-ba is-same">
        <span className="sim-ba-now">{fmtP6Date(after)}</span>
      </span>
    );
  }
  return (
    <span className="sim-ba">
      <span className="sim-ba-now">{fmtP6Date(after)}</span>
      <span className="sim-ba-was">was {fmtP6Date(before)}</span>
    </span>
  );
}

function FloatPair({ before, after }: { before: number | null; after: number | null }) {
  const same = before === after || (before != null && after != null && Math.abs(before - after) < 0.05);
  if (same) return <FloatBadge days={after} />;
  return (
    <span className="sim-float-pair">
      <FloatBadge days={before} />
      <ArrowRightIcon className="icon" />
      <FloatBadge days={after} />
    </span>
  );
}

// --- headline ------------------------------------------------------------------------

function Summary({ result }: { result: SimResult }) {
  const pf = result.project_finish;
  const c = result.counts;
  const r = Math.round(pf.delta_days * 10) / 10;
  const biggest = [...result.milestones].sort((a, b) => b.finish_delta_days - a.finish_delta_days)[0];
  return (
    <div className="kpi-row">
      <div className="card kpi accent-top">
        <span className="kpi-label">Project finish</span>
        <span className="kpi-value sim-kpi-date">{fmtP6Date(pf.simulated)}</span>
        <span className="kpi-sub">
          was {fmtP6Date(pf.unchanged)}
          {r > 0 ? (
            <span className="chip chip-crit">{signedDays(r)} later</span>
          ) : r < 0 ? (
            <span className="chip chip-good">{signedDays(r)} earlier</span>
          ) : (
            <span className="chip chip-neutral">No change</span>
          )}
        </span>
      </div>
      <div className="card kpi">
        <span className="kpi-label">Activities moved</span>
        <span className="kpi-value">{c.moved.toLocaleString()}</span>
        <span className="kpi-sub">
          {c.later.toLocaleString()} later · {c.earlier.toLocaleString()} earlier
        </span>
      </div>
      <div className="card kpi">
        <span className="kpi-label">Milestones moved</span>
        <span className="kpi-value">
          {c.milestones_moved} <span className="sim-kpi-of">of {c.milestones_total}</span>
        </span>
        <span className="kpi-sub">
          {biggest && biggest.finish_delta_days > 0.05
            ? `Largest slip ${signedDays(biggest.finish_delta_days)} · ${biggest.external_id}`
            : c.milestones_moved
              ? "None later"
              : "Unchanged"}
        </span>
      </div>
      <div className="card kpi">
        <span className="kpi-label">Critical activities</span>
        <span className="kpi-value">{c.critical_after.toLocaleString()}</span>
        <span className="kpi-sub">
          {c.joined_critical || c.left_critical
            ? `was ${c.critical_before} · ${c.joined_critical} joined, ${c.left_critical} left`
            : "Unchanged"}
        </span>
      </div>
    </div>
  );
}

// --- milestone slip chart -------------------------------------------------------

function MilestoneChart({ result }: { result: SimResult }) {
  const [all, setAll] = useState(false);
  const rows = useMemo(() => {
    const date = (m: SimRow) => m.finish_after ?? m.start_after ?? "";
    return [...result.milestones].sort(
      (a, b) =>
        Number(Boolean(b.is_project_finish)) - Number(Boolean(a.is_project_finish)) ||
        Number(b.direction !== "same") - Number(a.direction !== "same") ||
        b.finish_delta_days - a.finish_delta_days ||
        date(a).localeCompare(date(b)),
    );
  }, [result.milestones]);
  if (rows.length === 0) return null;

  const dateOf = (m: SimRow, side: "before" | "after") =>
    (side === "before" ? m.finish_before ?? m.start_before : m.finish_after ?? m.start_after) ?? null;
  const stamps = rows.flatMap((m) => [dateOf(m, "before"), dateOf(m, "after")]).filter(Boolean) as string[];
  stamps.push(result.simulation_data_date);
  const t = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
  const pad = 14 * 86_400_000;
  const lo = Math.min(...stamps.map(t)) - pad;
  const hi = Math.max(...stamps.map(t)) + pad;
  const pos = (iso: string | null) => (iso ? ((t(iso) - lo) / (hi - lo)) * 100 : 0);

  // Month ticks, thinned to about eight.
  const ticks: { label: string; at: number }[] = [];
  const start = new Date(lo);
  const cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1));
  const months: Date[] = [];
  while (cursor.getTime() < hi) {
    months.push(new Date(cursor));
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  const step = Math.max(1, Math.ceil(months.length / 8));
  months.forEach((m, i) => {
    if (i % step === 0)
      ticks.push({ label: `${MONTHS[m.getUTCMonth()]} ${String(m.getUTCFullYear()).slice(2)}`, at: ((m.getTime() - lo) / (hi - lo)) * 100 });
  });

  const shown = all ? rows : rows.slice(0, 8);
  const dd = pos(result.simulation_data_date);
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Milestones</div>
          <div className="card-title-sub">
            Hollow: without your changes · filled: with them · dashed line: simulation data date
          </div>
        </div>
      </div>
      <div className="sim-ms">
        <div className="sim-ms-axis" aria-hidden="true">
          <span />
          <div className="sim-ms-ticks">
            {ticks.map((tk) => (
              <span key={tk.label} style={{ left: `${tk.at}%` }}>
                {tk.label}
              </span>
            ))}
          </div>
          <span />
        </div>
        {shown.map((m) => {
          const was = dateOf(m, "before");
          const now = dateOf(m, "after");
          const a = pos(was);
          const b = pos(now);
          const tone = m.direction === "later" ? " is-later" : m.direction === "earlier" ? " is-earlier" : "";
          const label = `${m.external_id} ${m.name}: ${fmtP6Date(was)} to ${fmtP6Date(now)}, ${
            m.direction === "same" ? "no change" : `${Math.abs(Math.round(m.finish_delta_days * 10) / 10)} working days ${m.direction}`
          }`;
          return (
            <div key={m.id} className={`sim-ms-row${m.is_project_finish ? " is-finish" : ""}`} role="img" aria-label={label}>
              <div className="sim-ms-label">
                <div className="sim-ms-name" title={m.name}>
                  {m.name}
                </div>
                <div className="sim-ms-sub">
                  {m.external_id}
                  {m.is_project_finish ? " · project finish" : ""}
                </div>
              </div>
              <div className="sim-ms-track">
                <span className="sim-ms-dd" style={{ left: `${dd}%` }} />
                {was !== now && (
                  <span className={`sim-ms-span${tone}`} style={{ left: `${Math.min(a, b)}%`, width: `${Math.abs(b - a)}%` }} />
                )}
                <span className="sim-ms-was" style={{ left: `${a}%` }} title={`Without changes: ${fmtP6Date(was)}`} />
                <span className={`sim-ms-now${tone}`} style={{ left: `${b}%` }} title={`With changes: ${fmtP6Date(now)}`} />
              </div>
              <div className="sim-ms-delta">
                <Delta days={m.finish_delta_days} />
              </div>
            </div>
          );
        })}
        {rows.length > 8 && (
          <div className="sim-more">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAll((v) => !v)}>
              {all ? "Show the first 8" : `Show all ${rows.length} milestones`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// --- moved activities ---------------------------------------------------------------

function DriverCell({ row, onJump }: { row: SimRow; onJump: (id: string) => void }) {
  const d = row.driver;
  if (d.kind === "edit") return <span className="chip chip-info">Your change</span>;
  if (d.kind === "predecessor") {
    return (
      <span className="sim-driver">
        <button type="button" className="sim-driver-id" onClick={() => onJump(d.external_id)} title={d.name}>
          {d.external_id}
        </button>
        <span className="fp-link">{linkText(d.link_type, d.lag_days)}</span>
      </span>
    );
  }
  return <span className="chip chip-neutral">{driverText(d)}</span>;
}

function Chain({ row, byId, edits }: { row: SimRow; byId: Map<string, SimRow>; edits: Map<string, string> }) {
  const chain = walkChain(row, byId);
  const [expanded, setExpanded] = useState(false);
  if (chain.length === 1 && !row.is_edited) {
    return (
      <p className="sim-chain-none">
        {row.critical_before !== row.critical_after && row.direction === "same"
          ? `Its dates didn't move; its total float did, and it is ${row.critical_after ? "now" : "no longer"} critical.`
          : `Not driven through a chain from your changes — it now starts from: ${driverText(row.driver)}.`}
      </p>
    );
  }
  const origin = chain[0];
  const long = chain.length > 8 && !expanded;
  const shown = long ? [...chain.slice(0, 3), null, ...chain.slice(-3)] : chain;
  return (
    <>
      <div className="sim-chain-title">
        {row.direction === "earlier" ? "Released by your change, through:" : "Moved by your change, through:"}
      </div>
      <ol className="sim-chain">
        {shown.map((step, i) =>
          step === null ? (
            <li key="gap" className="sim-chain-gap">
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setExpanded(true)}>
                … {chain.length - 6} more steps
              </button>
            </li>
          ) : (
            <li key={step.external_id} className={step === origin ? "is-origin" : undefined}>
              <span className="sim-chain-name">
                <span className="actid">{step.external_id}</span>
                {step.name}
              </span>
              <Delta days={step.finish_delta_days} />
              <span className="sim-chain-date">{fmtP6Date(step.finish_after ?? step.start_after)}</span>
              <span className="sim-chain-link">
                {step === origin
                  ? `Your change: ${edits.get(step.external_id) ?? "edited"}`
                  : step.cause
                    ? `← ${linkText(step.cause.link_type, step.cause.lag_days)} from ${step.cause.external_id}`
                    : ""}
              </span>
            </li>
          ),
        )}
      </ol>
    </>
  );
}

function MovedTable({ result, projectCode }: { result: SimResult; projectCode: string }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "delta", dir: -1 });
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);

  const byId = useMemo(() => {
    const m = new Map<string, SimRow>();
    for (const r of result.moved) m.set(r.external_id, r);
    return m;
  }, [result.moved]);
  const edits = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of result.moved) if (r.driver.kind === "edit") m.set(r.external_id, r.driver.summary);
    return m;
  }, [result.moved]);

  const counts = useMemo(
    () => ({
      all: result.moved.length,
      later: result.moved.filter((r) => r.direction === "later").length,
      earlier: result.moved.filter((r) => r.direction === "earlier").length,
      critical: result.moved.filter((r) => r.critical_after).length,
    }),
    [result.moved],
  );

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = result.moved.filter(
      (r) =>
        (filter === "all" || (filter === "critical" ? r.critical_after : r.direction === filter)) &&
        (!q || r.external_id.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)),
    );
    const finish = (r: SimRow) => r.finish_after ?? r.start_after ?? "";
    list.sort((a, b) => {
      if (a.is_edited !== b.is_edited) return a.is_edited ? -1 : 1;
      if (sort.key === "id") return sort.dir * a.external_id.localeCompare(b.external_id);
      if (sort.key === "finish") return sort.dir * finish(a).localeCompare(finish(b));
      return sort.dir * (a.finish_delta_days - b.finish_delta_days) || finish(a).localeCompare(finish(b));
    });
    return list;
  }, [result.moved, filter, query, sort]);

  function toggle(id: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function jump(id: string) {
    if (!byId.has(id)) return;
    const idx = rows.findIndex((r) => r.external_id === id);
    if (idx < 0) {
      setFilter("all");
      setQuery("");
    } else if (idx >= limit) {
      setLimit(idx + 1);
    }
    setFlash(id);
    setTimeout(() => {
      document.getElementById(`sim-row-${id}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
      document.getElementById(`sim-row-${id}`)?.focus();
    }, 30);
    setTimeout(() => setFlash((f) => (f === id ? null : f)), 2000);
  }

  function sortHead(k: SortKey, label: string, className?: string) {
    const active = sort.key === k;
    return (
      <th className={className} aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
        <button
          type="button"
          className="pf-sort"
          onClick={() => setSort((s) => ({ key: k, dir: s.key === k ? (s.dir === 1 ? -1 : 1) : k === "delta" ? -1 : 1 }))}
        >
          {label}
          {active && <ChevronDownIcon className={`icon icon-sm${sort.dir === 1 ? " sim-sort-up" : ""}`} />}
        </button>
      </th>
    );
  }

  const shown = rows.slice(0, limit);
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Moved activities</div>
          <div className="card-title-sub">
            Every activity whose dates or critical status changed. Expand a row to trace it back to your change.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => downloadText(movedCsv(rows), `${projectCode}-simulation-${fmtP6Date(result.simulation_data_date)}.csv`)}
          disabled={rows.length === 0}
        >
          <DownloadIcon className="icon" />
          Export CSV
        </button>
      </div>
      <div className="sim-toolbar">
        <div className="segmented" role="group" aria-label="Filter moved activities">
          {(["all", "later", "earlier", "critical"] as Filter[]).map((f) => (
            <button key={f} type="button" className={filter === f ? "active" : undefined} onClick={() => setFilter(f)}>
              {f === "all" ? "All" : f === "later" ? "Later" : f === "earlier" ? "Earlier" : "Critical"}
              <span className="sim-count">{counts[f]}</span>
            </button>
          ))}
        </div>
        <input
          type="search"
          className="sim-search"
          placeholder="Search ID or name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search moved activities"
        />
        <span className="sim-toolbar-count">
          {rows.length > shown.length ? `Showing ${shown.length} of ${rows.length}` : `${rows.length} shown`}
          {result.truncated && " · list capped, export for the rest"}
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="empty-state">No moved activities match this filter.</p>
      ) : (
        <div className="table-wrap">
          <table className="sim-moved">
            <thead>
              <tr>
                <th className="sim-cell-expand" aria-label="Expand" />
                {sortHead("id", "Activity")}
                <th className="sim-col-start">Start</th>
                {sortHead("finish", "Finish")}
                {sortHead("delta", "Δ finish", "num")}
                <th>Total float</th>
                <th>Driven by</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const isOpen = open.has(r.external_id);
                const cls = [r.critical_after ? "critical" : "", flash === r.external_id ? "selected" : ""].filter(Boolean).join(" ");
                return (
                  <Fragment key={r.external_id}>
                    <tr id={`sim-row-${r.external_id}`} tabIndex={-1} className={cls || undefined}>
                      <td className="sim-cell-expand">
                        <button
                          type="button"
                          className="sim-expand"
                          aria-expanded={isOpen}
                          aria-controls={`sim-chain-${r.external_id}`}
                          aria-label={`${isOpen ? "Hide" : "Show"} why ${r.external_id} moved`}
                          onClick={() => toggle(r.external_id)}
                        >
                          <ChevronDownIcon className="icon" />
                        </button>
                      </td>
                      <td>
                        <div className="subname">
                          {r.name}
                          {r.is_edited && <span className="chip chip-info">Your change</span>}
                          {r.critical_after && !r.critical_before && <span className="chip chip-crit">Now critical</span>}
                          {r.critical_before && !r.critical_after && <span className="chip chip-neutral">Off critical</span>}
                        </div>
                        <div className="actid">
                          {r.external_id}
                          {r.wbs_name ? ` · ${r.wbs_name}` : ""}
                        </div>
                      </td>
                      <td className="sim-col-start">
                        <BeforeAfter before={r.start_before} after={r.start_after} />
                      </td>
                      <td>
                        <BeforeAfter before={r.finish_before} after={r.finish_after} />
                      </td>
                      <td className="num">
                        <Delta days={r.finish_delta_days} />
                      </td>
                      <td>
                        <FloatPair before={r.total_float_before_days} after={r.total_float_after_days} />
                      </td>
                      <td>
                        <DriverCell row={r} onJump={jump} />
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="sim-chain-row" id={`sim-chain-${r.external_id}`}>
                        <td colSpan={7}>
                          <Chain row={r} byId={byId} edits={edits} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > shown.length && (
        <div className="sim-more">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setLimit((l) => l + PAGE)}>
            Show {Math.min(PAGE, rows.length - shown.length)} more
          </button>
        </div>
      )}
    </div>
  );
}

// --- the whole results section ---------------------------------------------------

export function SimResults({
  result,
  stale,
  running,
  projectCode,
  onRerun,
}: {
  result: SimResult;
  stale: boolean;
  running: boolean;
  projectCode: string;
  onRerun: () => void;
}) {
  const pf = result.project_finish;
  const ddShift = result.simulation_data_date !== result.current_data_date;
  const nothing = result.moved.length === 0;
  return (
    <section className="sim-results" aria-busy={running}>
      <div className="sim-results-head">
        <h2 className="sim-results-title" id="sim-results-title" tabIndex={-1}>
          Results
        </h2>
        <span className="sim-results-meta">
          As of {fmtP6Date(result.simulation_data_date)}
          {result.revision_label ? ` · on ${result.revision_label}` : ""} · {result.total_activities.toLocaleString()} activities rescheduled
          {result.excluded_summary ? ` (${result.excluded_summary} summary / level-of-effort left out)` : ""}
        </span>
      </div>

      {stale && (
        <div className="banner warn" role="status">
          <AlertTriangleIcon className="icon" />
          <span className="banner-text">The scenario changed after this run, so these results are out of date.</span>
          <div className="banner-actions">
            <button type="button" className="btn btn-primary btn-sm" onClick={onRerun} disabled={running}>
              Run again
            </button>
          </div>
        </div>
      )}

      {ddShift && (
        <div className="banner" role="note">
          <span className="banner-text">
            Moving the data date to {fmtP6Date(result.simulation_data_date)} on its own moves{" "}
            <b>{result.counts.data_date_moved.toLocaleString()}</b> unfinished activit
            {result.counts.data_date_moved === 1 ? "y" : "ies"} and the finish by{" "}
            <b className="mono">{signedDays(pf.data_date_delta_days)}</b> ({fmtP6Date(pf.current)} → {fmtP6Date(pf.unchanged)}). The
            results below are your changes on top of that; together they move the finish{" "}
            <b className="mono">{signedDays(pf.total_delta_days)}</b>.
          </span>
        </div>
      )}

      {result.warnings.length > 0 && (
        <div className="banner warn" role="status">
          <AlertTriangleIcon className="icon" />
          <ul className="banner-text sim-warnings">
            {result.warnings.map((w, i) => (
              <li key={i}>{w.message}</li>
            ))}
          </ul>
        </div>
      )}

      <Summary result={result} />

      {!nothing && result.moved.every((r) => r.is_edited) && (
        <div className="banner good" role="status">
          <span className="banner-text">
            Nothing else moved: your changes are absorbed by float, so the project finish holds at {fmtP6Date(pf.simulated)}.
          </span>
        </div>
      )}

      {nothing ? (
        <div className="banner good" role="status">
          <span className="banner-text">
            No changes in this scenario, so nothing moved because of one. Add a change to see what it moves on top of the
            new data date.
          </span>
        </div>
      ) : (
        <>
          <MilestoneChart result={result} />
          <MovedTable result={result} projectCode={projectCode} />
        </>
      )}
    </section>
  );
}
