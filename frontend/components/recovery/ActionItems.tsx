"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { ChevronDownIcon, ChevronUpIcon, XIcon } from "@/components/icons";
import type { RecoveryItemStatusValue, RecoveryPlanItem } from "@/lib/types";

const STATUS_GLYPH: Record<RecoveryItemStatusValue, string> = {
  open: "○",
  in_progress: "◐",
  done: "✓",
  dropped: "✕",
};
const STATUS_CYCLE: RecoveryItemStatusValue[] = ["open", "in_progress", "done", "dropped"];

export function ActionItems({
  projectId,
  planId,
  items,
  editable,
  trackable,
  onChanged,
}: {
  projectId: string;
  planId: string;
  items: RecoveryPlanItem[];
  editable: boolean; // full edit (author, plan in draft/needs_revision)
  trackable: boolean; // may cycle item status even on an accepted plan
  onChanged: () => void;
}) {
  const { showToast } = useToast();
  const [busy, setBusy] = useState(false);
  const base = `/projects/${projectId}/recovery-plan/plans/${planId}`;

  async function call(fn: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      onChanged();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  }

  const patchItem = (id: string, body: Record<string, unknown>) =>
    call(() => api.patch(`${base}/items/${id}`, body));

  function cycleStatus(item: RecoveryPlanItem) {
    const next = STATUS_CYCLE[(STATUS_CYCLE.indexOf(item.status) + 1) % STATUS_CYCLE.length];
    patchItem(item.id, { status: next, completed_at: next === "done" ? new Date().toISOString().slice(0, 10) : null });
  }

  function move(idx: number, dir: -1 | 1) {
    const next = [...items];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    call(() => api.put(`${base}/items/order`, { ordered_item_ids: next.map((i) => i.id) }));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".3rem" }}>
      {items.length === 0 && !editable && (
        <p className="empty-state" style={{ padding: ".5rem 0" }}>No action items.</p>
      )}
      {items.map((item, idx) => (
        <div
          key={item.id}
          style={{ display: "flex", alignItems: "center", gap: ".4rem", padding: ".15rem 0" }}
        >
          <span className="mono" style={{ color: "var(--text-muted)", width: 16, flex: "none" }}>{idx + 1}</span>
          <button
            onClick={() => (trackable || editable) && cycleStatus(item)}
            title={item.status}
            style={{
              background: "none", border: "none", cursor: trackable || editable ? "pointer" : "default",
              fontSize: "1rem", width: 22, flex: "none",
              color: item.status === "done" ? "var(--good)" : item.status === "dropped" ? "var(--text-muted)" : "var(--text-secondary)",
            }}
          >
            {STATUS_GLYPH[item.status]}
          </button>
          <input
            defaultValue={item.action}
            disabled={!editable}
            onBlur={(e) => e.target.value !== item.action && patchItem(item.id, { action: e.target.value })}
            className={editable ? "field-editable" : undefined}
            style={{ flex: 1, minWidth: 120 }}
          />
          <input
            defaultValue={item.owner_name ?? ""}
            disabled={!editable}
            placeholder="Owner"
            onBlur={(e) => e.target.value !== (item.owner_name ?? "") && patchItem(item.id, { owner_name: e.target.value || null })}
            className={editable ? "field-editable" : undefined}
            style={{ width: 120, flex: "none" }}
          />
          <input
            type="date"
            defaultValue={item.target_date ?? ""}
            disabled={!editable}
            onBlur={(e) => e.target.value !== (item.target_date ?? "") && patchItem(item.id, { target_date: e.target.value || null })}
            className={editable ? "field-editable" : undefined}
            style={{ width: 140, flex: "none" }}
          />
          {editable && (
            <span style={{ display: "flex", flex: "none" }}>
              <button className="btn btn-ghost btn-sm" onClick={() => move(idx, -1)} aria-label="Move up">
                <ChevronUpIcon className="icon" style={{ width: 12, height: 12 }} />
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => move(idx, 1)} aria-label="Move down">
                <ChevronDownIcon className="icon" style={{ width: 12, height: 12 }} />
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => call(() => api.delete(`${base}/items/${item.id}`))}
                aria-label="Remove"
              >
                <XIcon className="icon" style={{ width: 12, height: 12 }} />
              </button>
            </span>
          )}
        </div>
      ))}
      {editable && (
        <button
          className="btn btn-secondary btn-sm"
          style={{ alignSelf: "flex-start", marginTop: ".3rem" }}
          disabled={busy}
          onClick={() => call(() => api.post(`${base}/items`, { action: "New action" }))}
        >
          + Add action item
        </button>
      )}
    </div>
  );
}
