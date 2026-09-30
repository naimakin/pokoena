"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { ChevronDownIcon, ChevronUpIcon, XIcon } from "@/components/icons";

// Shared itemised-action-list editor for Recovery Plan and Risk Mitigation.
// `basePath` is the plan/risk URL; this appends /items, /items/{id}, /items/order.
export interface ActionItemShape {
  id: string;
  order_index: number;
  action: string;
  owner_name: string | null;
  target_date: string | null;
  status: "open" | "in_progress" | "done" | "dropped";
  completed_at: string | null;
}

const STATUS_GLYPH: Record<ActionItemShape["status"], string> = {
  open: "○",
  in_progress: "◐",
  done: "✓",
  dropped: "✕",
};
const STATUS_CYCLE: ActionItemShape["status"][] = ["open", "in_progress", "done", "dropped"];

export function ActionItems({
  basePath,
  items,
  editable,
  trackable,
  onChanged,
}: {
  basePath: string;
  items: ActionItemShape[];
  editable: boolean; // full edit (author, plan editable)
  trackable: boolean; // may cycle item status even once accepted
  onChanged: () => void;
}) {
  const { showToast } = useToast();
  const [busy, setBusy] = useState(false);

  async function call(fn: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      onChanged();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Update failed.", "error");
    } finally {
      setBusy(false);
    }
  }

  const patchItem = (id: string, body: Record<string, unknown>) =>
    call(() => api.patch(`${basePath}/items/${id}`, body));

  function cycleStatus(item: ActionItemShape) {
    const next = STATUS_CYCLE[(STATUS_CYCLE.indexOf(item.status) + 1) % STATUS_CYCLE.length];
    patchItem(item.id, {
      status: next,
      completed_at: next === "done" ? new Date().toISOString().slice(0, 10) : null,
    });
  }

  function move(idx: number, dir: -1 | 1) {
    const next = [...items];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    call(() => api.put(`${basePath}/items/order`, { ordered_item_ids: next.map((i) => i.id) }));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".3rem" }}>
      {items.length === 0 && !editable && (
        <p className="empty-state" style={{ padding: ".5rem 0" }}>No action items.</p>
      )}
      {items.map((item, idx) => (
        <div key={item.id} style={{ display: "flex", alignItems: "center", gap: ".4rem", padding: ".15rem 0" }}>
          <span className="mono" style={{ color: "var(--text-muted)", width: 16, flex: "none" }}>{idx + 1}</span>
          <button
            onClick={() => (trackable || editable) && cycleStatus(item)}
            title={item.status}
            aria-label={`Status: ${item.status}`}
            style={{
              background: "none",
              border: "none",
              cursor: trackable || editable ? "pointer" : "default",
              fontSize: "1rem",
              width: 22,
              flex: "none",
              color:
                item.status === "done"
                  ? "var(--good)"
                  : item.status === "dropped"
                    ? "var(--text-muted)"
                    : "var(--text-secondary)",
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
                onClick={() => call(() => api.delete(`${basePath}/items/${item.id}`))}
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
          onClick={() => call(() => api.post(`${basePath}/items`, { action: "New action" }))}
        >
          + Add action item
        </button>
      )}
    </div>
  );
}
