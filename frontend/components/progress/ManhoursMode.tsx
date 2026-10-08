"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import type { Activity, WbsNode } from "@/lib/types";
import { fmtUnitsPercent } from "@/lib/wbs-tree";
import { WbsGrid } from "./WbsGrid";

type Draft = { burnedHours: string; physicalPct: string };

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ManhoursMode({
  hidden,
  nodes,
  activities,
  projectId,
  hasActiveBaseline,
  collapsed,
  onToggle,
  onDirtyChange,
}: {
  hidden: boolean;
  nodes: WbsNode[];
  activities: Activity[];
  projectId: string;
  hasActiveBaseline: boolean;
  collapsed: Set<string>;
  onToggle: (wbsId: string) => void;
  onDirtyChange: (count: number) => void;
}) {
  const { showToast } = useToast();
  const [entryDate, setEntryDate] = useState(todayIso());
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [submitting, setSubmitting] = useState(false);

  const pending = useMemo(
    () => Object.entries(drafts).filter(([, d]) => d?.burnedHours && Number(d.burnedHours) > 0),
    [drafts],
  );
  useEffect(() => onDirtyChange(pending.length), [pending.length, onDirtyChange]);

  function setDraft(id: string, field: keyof Draft, value: string) {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], [field]: value } as Draft }));
  }

  async function submit() {
    if (!hasActiveBaseline || pending.length === 0) return;
    setSubmitting(true);
    try {
      const entries = pending.map(([id, d]) => ({
        activity_id: id,
        entry_date: entryDate,
        burned_manhours_daily: Number(d.burnedHours),
        physical_pct_snapshot: d.physicalPct ? Number(d.physicalPct) : undefined,
      }));
      const res = await api.post<{ written: number; out_of_sequence_count: number }>(
        `/projects/${projectId}/evm/progress`,
        { entries },
      );
      showToast(
        `${res.written} progress entr${res.written === 1 ? "y" : "ies"} recorded` +
          (res.out_of_sequence_count > 0 ? ` (${res.out_of_sequence_count} out of sequence)` : ""),
      );
      setDrafts({});
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to submit progress.", "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div hidden={hidden}>
      <div style={{ padding: "0.9rem 1rem 0" }}>
        {!hasActiveBaseline && (
          <div className="banner warn" style={{ marginBottom: "1rem" }}>
            <span className="banner-text">
              No active baseline — burned-hours entry needs one locked (Programme → Baselines).
            </span>
          </div>
        )}
        <div style={{ display: "flex", alignItems: "flex-end", gap: ".6rem", marginBottom: ".8rem" }}>
        <div className="field" style={{ maxWidth: 180 }}>
          <label htmlFor="pg-entry-date">Entry date</label>
          <input id="pg-entry-date" type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
        </div>
        <button
          className="btn btn-primary"
          onClick={submit}
          disabled={submitting || pending.length === 0 || !hasActiveBaseline}
        >
          {submitting ? "Submitting…" : `Submit Progress (${pending.length})`}
        </button>
        </div>
      </div>

      <WbsGrid
        nodes={nodes}
        activities={activities}
        collapsed={collapsed}
        onToggle={onToggle}
        colCount={3}
        idColumn
        bandCells={{
          labelSpan: 2,
          render: (row) => (
            <>
              <td className="num" title="Units % complete: Σ actual / Σ budgeted labor hours of the activities shown">
                {fmtUnitsPercent(row)}
              </td>
              <td colSpan={2} />
            </>
          ),
        }}
        header={
          <>
            <th>Activity</th>
            <th style={{ width: 140 }}>Activity ID</th>
            <th style={{ width: 90 }}>%</th>
            <th style={{ width: 160 }}>Burned Hours</th>
            <th style={{ width: 160 }}>New %</th>
          </>
        }
        renderActivityCells={(a) => (
          <>
            <td className="num">{a.percent_complete}%</td>
            <td className="field-editable">
              <input
                type="number"
                min={0}
                step="0.5"
                placeholder="0"
                value={drafts[a.id]?.burnedHours ?? ""}
                onChange={(e) => setDraft(a.id, "burnedHours", e.target.value)}
              />
            </td>
            <td className="field-editable">
              <input
                type="number"
                min={0}
                max={100}
                placeholder={String(a.percent_complete)}
                value={drafts[a.id]?.physicalPct ?? ""}
                onChange={(e) => setDraft(a.id, "physicalPct", e.target.value)}
              />
            </td>
          </>
        )}
      />
    </div>
  );
}
