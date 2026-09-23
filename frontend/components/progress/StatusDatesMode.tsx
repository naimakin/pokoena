"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import type { Activity, ActivityBatchResult, WbsNode } from "@/lib/types";
import { WbsGrid } from "./WbsGrid";

type Draft = { actual_start?: string | null; actual_finish?: string | null; percent_complete?: number };
type DraftMap = Record<string, Draft>;

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not Started",
  in_progress: "In Progress",
  complete: "Completed",
};
const STATUS_CHIP: Record<string, string> = {
  not_started: "chip-neutral",
  in_progress: "chip-active",
  complete: "chip-good",
};

function resolved(a: Activity, d: Draft | undefined) {
  return {
    actual_start: d && "actual_start" in d ? d.actual_start || null : a.actual_start,
    actual_finish: d && "actual_finish" in d ? d.actual_finish || null : a.actual_finish,
    percent_complete: d && "percent_complete" in d ? d.percent_complete ?? 0 : a.percent_complete,
  };
}

function fieldChanged(a: Activity, d: Draft | undefined, key: keyof Draft): boolean {
  if (!d || !(key in d)) return false;
  const r = resolved(a, d);
  if (key === "percent_complete") return r.percent_complete !== a.percent_complete;
  return (r[key] || null) !== (a[key] || null);
}

function rowDirty(a: Activity, d: Draft | undefined): boolean {
  return fieldChanged(a, d, "actual_start") || fieldChanged(a, d, "actual_finish") || fieldChanged(a, d, "percent_complete");
}

function clientError(a: Activity, d: Draft): string | null {
  const r = resolved(a, d);
  if (r.actual_finish && !r.actual_start) return "Actual Finish needs an Actual Start";
  if (r.actual_start && r.actual_finish && r.actual_start > r.actual_finish) return "Actual Finish is before Actual Start";
  return null;
}

export function StatusDatesMode({
  hidden,
  nodes,
  activities,
  allActivities,
  dataDate,
  projectId,
  canEdit,
  collapsed,
  onToggle,
  onActivitiesUpdated,
  onDirtyChange,
}: {
  hidden: boolean;
  nodes: WbsNode[];
  activities: Activity[];
  allActivities: Activity[];
  dataDate: string | null;
  projectId: string;
  canEdit: boolean;
  collapsed: Set<string>;
  onToggle: (wbsId: string) => void;
  onActivitiesUpdated: (rows: Activity[]) => void;
  onDirtyChange: (count: number) => void;
}) {
  const { showToast } = useToast();
  const [drafts, setDrafts] = useState<DraftMap>({});
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const activityById = useMemo(() => new Map(allActivities.map((a) => [a.id, a])), [allActivities]);
  const dirtyIds = useMemo(
    () => Object.keys(drafts).filter((id) => activityById.get(id) && rowDirty(activityById.get(id)!, drafts[id])),
    [drafts, activityById],
  );

  useEffect(() => onDirtyChange(dirtyIds.length), [dirtyIds.length, onDirtyChange]);

  function setDraft(id: string, patch: Draft) {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }
  function revertRow(id: string) {
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  async function save(ids: string[]) {
    if (saving || ids.length === 0) return;
    const errs: Record<string, string> = {};
    const updates = ids.map((id) => {
      const a = activityById.get(id)!;
      const d = drafts[id];
      const err = clientError(a, d);
      if (err) errs[id] = err;
      return { id, ...d };
    });
    if (Object.keys(errs).length > 0) {
      setRowErrors((prev) => ({ ...prev, ...errs }));
      showToast("Fix the highlighted rows first.");
      return;
    }

    setSaving(true);
    try {
      const res = await api.patch<ActivityBatchResult>(`/activities?project_id=${projectId}`, { updates });
      if (res.saved.length > 0) onActivitiesUpdated(res.saved);
      const savedIds = new Set(res.saved.map((r) => r.id));
      const failedById = new Map(res.failed.map((f) => [f.id, f.error]));
      setDrafts((prev) => {
        const next = { ...prev };
        for (const id of ids) if (savedIds.has(id)) delete next[id];
        return next;
      });
      setRowErrors((prev) => {
        const next = { ...prev };
        for (const id of ids) {
          if (savedIds.has(id)) delete next[id];
          else if (failedById.has(id)) next[id] = failedById.get(id)!;
        }
        return next;
      });
      if (res.failed.length > 0) showToast(`${res.saved.length} saved · ${res.failed.length} failed`);
      else showToast(`${res.saved.length} activit${res.saved.length === 1 ? "y" : "ies"} saved`);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  const afterDataDate = (v: string | null | undefined) => Boolean(v && dataDate && v > dataDate.slice(0, 10));

  return (
    <div hidden={hidden}>
      <WbsGrid
        nodes={nodes}
        activities={activities}
        collapsed={collapsed}
        onToggle={onToggle}
        colCount={5}
        header={
          <>
            <th>Activity</th>
            <th>Status</th>
            <th style={{ width: 150 }}>Actual Start</th>
            <th style={{ width: 150 }}>Actual Finish</th>
            <th style={{ width: 90 }}>%</th>
            <th style={{ width: 130 }} />
          </>
        }
        renderActivityCells={(a) => {
          const d = drafts[a.id];
          const r = resolved(a, d);
          const dirty = rowDirty(a, d);
          const err = rowErrors[a.id];
          return (
            <>
              <td>
                <span className={`chip ${STATUS_CHIP[r.actual_finish ? "complete" : r.actual_start ? "in_progress" : a.status]}`}>
                  {STATUS_LABEL[r.actual_finish ? "complete" : r.actual_start ? "in_progress" : a.status]}
                </span>
              </td>
              <td className={fieldChanged(a, d, "actual_start") ? "field-editable" : undefined}>
                <input
                  type="date"
                  disabled={!canEdit}
                  value={r.actual_start ?? ""}
                  onChange={(e) => setDraft(a.id, { actual_start: e.target.value || null })}
                />
                {afterDataDate(r.actual_start) && <div className="pg-warn">after data date</div>}
              </td>
              <td className={fieldChanged(a, d, "actual_finish") ? "field-editable" : undefined}>
                <input
                  type="date"
                  disabled={!canEdit}
                  value={r.actual_finish ?? ""}
                  onChange={(e) => setDraft(a.id, { actual_finish: e.target.value || null })}
                />
                {afterDataDate(r.actual_finish) && <div className="pg-warn">after data date</div>}
              </td>
              <td className={fieldChanged(a, d, "percent_complete") ? "field-editable" : undefined}>
                <input
                  type="number"
                  min={0}
                  max={100}
                  disabled={!canEdit}
                  value={r.percent_complete}
                  onChange={(e) => setDraft(a.id, { percent_complete: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })}
                />
                {r.percent_complete === 100 && !r.actual_finish && <div className="pg-warn">100% · no finish</div>}
              </td>
              <td>
                {err && <div className="pg-row-err">{err}</div>}
                {(dirty || err) && canEdit && (
                  <div className="pg-row-actions">
                    <button className="btn btn-primary btn-sm" disabled={saving} onClick={() => save([a.id])}>
                      Save
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => revertRow(a.id)}>
                      ↺
                    </button>
                  </div>
                )}
              </td>
            </>
          );
        }}
      />

      {dirtyIds.length > 0 && canEdit && (
        <div className="pg-subfooter">
          <span style={{ fontSize: ".8125rem", fontWeight: 600 }}>
            {dirtyIds.length} unsaved activit{dirtyIds.length === 1 ? "y" : "ies"}
          </span>
          <span className="spacer" />
          <button className="btn btn-ghost btn-sm" onClick={() => dirtyIds.forEach(revertRow)}>
            Revert all
          </button>
          <button className="btn btn-primary btn-sm" disabled={saving} onClick={() => save(dirtyIds)}>
            {saving ? "Saving…" : "Save all"}
          </button>
        </div>
      )}
    </div>
  );
}
