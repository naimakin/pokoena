"use client";

// The programme, as Activity Ledger shows it (WBS bands, Status / Start /
// Finish / Total Float / %), to pick and edit the activities of a scenario.
// A changed activity shows its scenario values; after a run, the last column
// shows where every moved activity now finishes.

import { useMemo, useState } from "react";
import { WbsGrid } from "@/components/progress/WbsGrid";
import { floatClass, fmtP6Date } from "@/components/reporting/format";
import { toDays } from "@/lib/duration";
import { displayFinish, displayStart, isMilestone } from "@/lib/schedule-dates";
import { deltaClass, draftDates, remainingDays, signedDays, type Draft, type SimResult, type SimRow } from "@/lib/simulation";
import type { Activity, WbsNode } from "@/lib/types";
import { StatusChip } from "./ScenarioSetup";

type Filter = "all" | "changed" | "in_progress" | "critical" | "moved";

function fmtFloat(days: number | null): string {
  if (days === null) return "—";
  return `${days >= 0 ? "" : "-"}${Math.abs(days).toFixed(1)}d`;
}

export function ProgrammeGrid({
  activities,
  nodes,
  drafts,
  result,
  stale,
  onOpen,
}: {
  activities: Activity[];
  nodes: WbsNode[];
  drafts: Map<string, Draft>;
  result: SimResult | null;
  stale: boolean;
  onOpen: (a: Activity) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const moved = useMemo(() => new Map<string, SimRow>((result?.moved ?? []).map((r) => [r.external_id, r])), [result]);
  const maxLevel = useMemo(() => (nodes.length ? Math.max(...nodes.map((n) => n.depth)) + 1 : 1), [nodes]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return activities.filter((a) => {
      if (q && !a.external_id.toLowerCase().includes(q) && !a.name.toLowerCase().includes(q)) return false;
      if (filter === "changed") return drafts.has(a.external_id);
      if (filter === "in_progress") return (drafts.get(a.external_id)?.status ?? a.status) === "in_progress";
      if (filter === "critical") return a.status !== "complete" && Boolean(a.is_critical);
      if (filter === "moved") return moved.has(a.external_id);
      return true;
    });
  }, [activities, query, filter, drafts, moved]);

  function toggle(wbsId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
  }

  const filters: { key: Filter; label: string; count?: number }[] = [
    { key: "all", label: "All" },
    { key: "changed", label: "Changed", count: drafts.size },
    { key: "in_progress", label: "In progress" },
    { key: "critical", label: "Critical" },
    ...(result ? [{ key: "moved" as Filter, label: "Moved", count: moved.size }] : []),
  ];

  return (
    <div className="card sim-programme">
      <div className="card-head">
        <div>
          <div className="card-title">Programme</div>
          <div className="card-title-sub">
            {activities.length.toLocaleString()} activities, as in Activity Ledger. Click one to change it in the scenario.
          </div>
        </div>
      </div>
      <div className="sim-toolbar">
        <div className="segmented" role="group" aria-label="Filter the programme">
          {filters.map((f) => (
            <button key={f.key} type="button" className={filter === f.key ? "active" : undefined} onClick={() => setFilter(f.key)}>
              {f.label}
              {f.count !== undefined && <span className="sim-count">{f.count}</span>}
            </button>
          ))}
        </div>
        <input
          type="search"
          className="sim-search"
          placeholder="Search ID or name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search activities"
        />
        {nodes.length > 0 && (
          <select
            className="select-sm sim-level"
            defaultValue=""
            aria-label="Collapse WBS to level"
            onChange={(e) => {
              const level = Number(e.target.value);
              if (level) setCollapsed(new Set(nodes.filter((n) => n.depth + 1 >= level).map((n) => n.wbs_id)));
              else setCollapsed(new Set());
              e.target.value = "";
            }}
          >
            <option value="" disabled>
              Collapse to…
            </option>
            <option value="0">Expand all</option>
            {Array.from({ length: maxLevel }, (_, i) => (
              <option key={i + 1} value={i + 1}>
                Level {i + 1}
              </option>
            ))}
          </select>
        )}
        <span className="sim-toolbar-count">
          {shown.length !== activities.length ? `${shown.length.toLocaleString()} of ${activities.length.toLocaleString()}` : ""}
        </span>
      </div>
      <WbsGrid
        nodes={nodes}
        activities={shown}
        collapsed={collapsed}
        onToggle={toggle}
        onActivityClick={onOpen}
        rowClassName={(a) => (drafts.has(a.external_id) ? "sim-row-changed" : undefined)}
        emptyLabel={filter === "changed" ? "No activity is changed in this scenario yet." : "No activities match."}
        colCount={7}
        header={
          <>
            <th>Activity</th>
            <th>Status</th>
            <th style={{ width: 110 }}>Start</th>
            <th style={{ width: 110 }}>Finish</th>
            <th style={{ width: 90 }}>Total Float</th>
            <th style={{ width: 60 }}>%</th>
            <th style={{ width: 90 }}>Remaining</th>
            <th style={{ width: 150 }} className={stale ? "sim-col-stale" : undefined} title="Where the activity finishes in the last run">
              Simulated finish
            </th>
          </>
        }
        renderActivityCells={(a) => {
          const d = drafts.get(a.external_id);
          const dates = d ? draftDates(a, d) : { start: displayStart(a), finish: displayFinish(a) };
          const tf = toDays(a.total_float_hours, a);
          const m = moved.get(a.external_id);
          return (
            <>
              <td>
                <StatusChip status={d?.status ?? a.status} />
                {d && <span className="chip chip-info sim-changed-chip">Changed</span>}
              </td>
              <td className="mono">{fmtP6Date(dates.start)}</td>
              <td className="mono">{fmtP6Date(dates.finish)}</td>
              <td className="mono">
                <span className={floatClass(tf)}>{fmtFloat(tf)}</span>
              </td>
              <td className="mono">{isMilestone(a) ? "—" : `${d?.percent_complete ?? a.percent_complete}%`}</td>
              <td className="mono">
                {isMilestone(a) || (d?.status ?? a.status) === "complete"
                  ? "—"
                  : `${Math.round((d?.remaining_days ?? remainingDays(a)) * 10) / 10}d`}
              </td>
              <td className={`mono${stale ? " sim-col-stale" : ""}`}>
                {!result ? (
                  <span className="sim-muted">—</span>
                ) : m ? (
                  <span className="sim-simfin">
                    {fmtP6Date(m.finish_after ?? m.start_after)}
                    <span className={deltaClass(m.finish_delta_days)}>{signedDays(m.finish_delta_days)}</span>
                  </span>
                ) : (
                  <span className="sim-muted">No change</span>
                )}
              </td>
            </>
          );
        }}
      />
    </div>
  );
}
