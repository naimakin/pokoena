"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { AlertTriangleIcon, CheckIcon, ClockIcon, FlagIcon, XIcon } from "@/components/icons";
import type {
  Activity,
  ActivityHistoryItem,
  ActivityRelationship,
  ActivityStatus,
  WbsNode,
} from "@/lib/types";

// Activity detail + edit, opened by clicking a row rather than editing in the
// grid. The grid stays a readable overview; everything you can do to one
// activity lives here, in the four things people actually come for: change its
// progress, read its P6 detail, see what it's wired to, and see what moved.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const TABS = [
  { key: "update", label: "Update" },
  { key: "details", label: "Details" },
  { key: "relationships", label: "Relationships" },
  { key: "history", label: "History" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const STATUS_OPTIONS: { value: ActivityStatus; label: string }[] = [
  { value: "not_started", label: "Not Started" },
  { value: "in_progress", label: "In Progress" },
  { value: "complete", label: "Completed" },
];

const STATUS_CHIP: Record<ActivityStatus, string> = {
  not_started: "chip-neutral",
  in_progress: "chip-active",
  complete: "chip-good",
};

const FIELD_LABELS: Record<string, string> = {
  status: "Status",
  percent_complete: "% Complete",
  actual_start: "Actual Start",
  actual_finish: "Actual Finish",
  remaining_duration_days: "Remaining Duration",
  is_important: "Important",
  tags: "Tags",
  notes: "Notes",
  planned_start: "Planned Start",
  planned_finish: "Planned Finish",
  early_start: "Early Start",
  early_finish: "Early Finish",
  total_float_hours: "Total Float",
  is_critical: "Critical",
};

// P6 convention (DD-MMM-YYYY) — see CLAUDE.md.
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${fmtDate(iso)} · ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function days(hours: number | null | undefined): string {
  return hours == null ? "—" : `${(hours / 8).toFixed(1)}d`;
}

/** Render a stored history value in the same shape the rest of the UI uses. */
function historyValue(field: string | null, raw: string | null): string {
  if (raw === null || raw === "") return "—";
  if (!field) return raw;
  if (field.endsWith("_start") || field.endsWith("_finish")) return fmtDate(raw);
  if (field === "total_float_hours") return days(Number(raw));
  if (field === "status") return STATUS_OPTIONS.find((s) => s.value === raw)?.label ?? raw;
  if (raw === "true") return "Yes";
  if (raw === "false") return "No";
  return raw;
}

type Draft = {
  status: ActivityStatus;
  actual_start: string | null;
  actual_finish: string | null;
  percent_complete: number;
  remaining_duration_days: number;
  is_important: boolean;
  tags: string[];
  notes: string;
};

function draftFrom(a: Activity): Draft {
  return {
    status: a.status,
    actual_start: a.actual_start,
    actual_finish: a.actual_finish,
    percent_complete: a.percent_complete,
    remaining_duration_days: a.remaining_duration_days,
    is_important: Boolean(a.is_important),
    tags: a.tags ?? [],
    notes: a.notes ?? "",
  };
}

export function ActivityModal({
  activity,
  canEdit,
  wbsNodes,
  snapshotOnly = false,
  onClose,
  onSaved,
}: {
  activity: Activity | null;
  canEdit: boolean;
  wbsNodes?: WbsNode[];
  // True when the row came from an earlier programme's frozen snapshot rather
  // than the live schedule. Those rows carry synthetic ids (uuid5 of the import
  // + the P6 activity id — see schedule_imports.py), so there is no server-side
  // activity to fetch relationships or history for; say so instead of
  // rendering an empty tab that reads as "this activity has no predecessors".
  snapshotOnly?: boolean;
  onClose: () => void;
  onSaved: (updated: Activity) => void;
}) {
  const { showToast } = useToast();
  const [tab, setTab] = useState<TabKey>("update");
  const [draft, setDraft] = useState<Draft | null>(() => (activity ? draftFrom(activity) : null));
  const [saving, setSaving] = useState(false);
  const [tagInput, setTagInput] = useState("");
  const [commentBody, setCommentBody] = useState("");
  const [posting, setPosting] = useState(false);

  const [relationships, setRelationships] = useState<ActivityRelationship[] | null>(null);
  const [history, setHistory] = useState<ActivityHistoryItem[] | null>(null);

  const activityId = activity?.id ?? null;

  useEffect(() => {
    if (!activityId) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [activityId, onClose]);

  const loadHistory = useCallback(async () => {
    if (!activityId || snapshotOnly) return;
    try {
      setHistory(await api.get<ActivityHistoryItem[]>(`/activities/${activityId}/history`));
    } catch {
      setHistory([]);
    }
  }, [activityId, snapshotOnly]);

  // Relationships and history are fetched the first time their tab is opened —
  // most people open the modal to change a percentage and never look at either.
  useEffect(() => {
    if (!activityId || snapshotOnly) return;
    if (tab === "relationships" && relationships === null) {
      api
        .get<ActivityRelationship[]>(`/activities/${activityId}/relationships`)
        .then(setRelationships)
        .catch(() => setRelationships([]));
    }
    if (tab === "history" && history === null) loadHistory();
  }, [tab, activityId, relationships, history, loadHistory, snapshotOnly]);

  const comments = useMemo(
    () => (history ?? []).filter((h) => h.kind === "comment"),
    [history],
  );

  // The Update tab shows the comment thread, so it needs the history too.
  useEffect(() => {
    if (activityId && tab === "update" && history === null) loadHistory();
  }, [tab, activityId, history, loadHistory]);

  if (!activity || !draft) return null;

  const wbsName = wbsNodes?.find((n) => n.wbs_id === activity.wbs_path);
  const isFinished = draft.status === "complete";
  const dirty =
    draft.status !== activity.status ||
    (draft.actual_start || null) !== (activity.actual_start || null) ||
    (draft.actual_finish || null) !== (activity.actual_finish || null) ||
    draft.percent_complete !== activity.percent_complete ||
    draft.remaining_duration_days !== activity.remaining_duration_days ||
    draft.is_important !== Boolean(activity.is_important) ||
    draft.tags.join("\u0000") !== (activity.tags ?? []).join("\u0000") ||
    draft.notes !== (activity.notes ?? "");

  const validationError =
    draft.actual_finish && !draft.actual_start
      ? "Actual Finish needs an Actual Start"
      : draft.actual_start && draft.actual_finish && draft.actual_start > draft.actual_finish
        ? "Actual Finish is before Actual Start"
        : null;

  /** Status is derived from the actual dates on the server (see
   *  _apply_progress_derivation), so picking one here sets those dates rather
   *  than sending a status the backend would just recompute. */
  function pickStatus(next: ActivityStatus) {
    setDraft((d) => {
      if (!d) return d;
      if (next === "not_started") {
        return { ...d, status: next, actual_start: null, actual_finish: null, percent_complete: 0 };
      }
      if (next === "in_progress") {
        return {
          ...d,
          status: next,
          actual_start: d.actual_start ?? todayIso(),
          actual_finish: null,
          percent_complete: d.percent_complete >= 100 ? 99 : d.percent_complete,
        };
      }
      return {
        ...d,
        status: next,
        actual_start: d.actual_start ?? todayIso(),
        actual_finish: d.actual_finish ?? todayIso(),
        percent_complete: 100,
        remaining_duration_days: 0,
      };
    });
  }

  function addTag() {
    const value = tagInput.trim();
    if (!value || draft!.tags.includes(value) || draft!.tags.length >= 20) {
      setTagInput("");
      return;
    }
    setDraft((d) => (d ? { ...d, tags: [...d.tags, value] } : d));
    setTagInput("");
  }

  async function save() {
    if (!activity || !draft || saving) return;
    if (validationError) {
      showToast(validationError);
      return;
    }
    setSaving(true);
    try {
      const updated = await api.patch<Activity>(`/activities/${activity.id}`, {
        actual_start: draft.actual_start,
        actual_finish: draft.actual_finish,
        percent_complete: draft.percent_complete,
        remaining_duration_days: draft.remaining_duration_days,
        is_important: draft.is_important,
        tags: draft.tags,
        notes: draft.notes.trim() ? draft.notes.trim() : null,
      });
      onSaved(updated);
      setDraft(draftFrom(updated));
      setHistory(null); // the save just wrote new timeline rows
      showToast("Activity saved");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save this activity.");
    } finally {
      setSaving(false);
    }
  }

  async function postComment() {
    const body = commentBody.trim();
    if (!activity || !body || posting) return;
    setPosting(true);
    try {
      await api.post(`/activities/${activity.id}/comments`, { body });
      setCommentBody("");
      setHistory(null);
      await loadHistory();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not post the comment.");
    } finally {
      setPosting(false);
    }
  }

  const predecessors = (relationships ?? []).filter((r) => r.successor_id === activity.id);
  const successors = (relationships ?? []).filter((r) => r.predecessor_id === activity.id);

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-lg act-modal" role="dialog" aria-modal="true" aria-label={activity.name}>
        <div className="modal-head act-modal-head">
          <div style={{ minWidth: 0 }}>
            <div className="act-modal-crumb">
              <span className="mono">{activity.external_id}</span>
              {wbsName && <span> · {wbsName.wbs_name}</span>}
              {activity.discipline && <span> · {activity.discipline}</span>}
            </div>
            <div className="modal-title act-modal-title">{activity.name}</div>
            <div className="act-modal-badges">
              <span className={`chip ${STATUS_CHIP[draft.status]}`}>
                {STATUS_OPTIONS.find((s) => s.value === draft.status)?.label}
              </span>
              {activity.is_critical && !isFinished && (
                <span className="chip chip-crit">
                  <AlertTriangleIcon className="icon" style={{ width: 11, height: 11 }} /> Critical
                </span>
              )}
              {draft.is_important && (
                <span className="chip chip-warn">
                  <FlagIcon className="icon" style={{ width: 11, height: 11 }} /> Important
                </span>
              )}
              <span className="act-modal-float">Total float {days(activity.total_float_hours)}</span>
            </div>
          </div>
          <button className="act-btn" onClick={onClose} aria-label="Close" title="Close">
            <XIcon className="icon" />
          </button>
        </div>

        <div className="act-modal-tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={tab === t.key ? "is-on" : undefined}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="modal-body act-modal-body">
          {/* ---------------- Update ---------------- */}
          {tab === "update" && (
            <>
              {!canEdit && (
                <p className="act-modal-note">
                  Read-only — you don&rsquo;t have edit rights on this activity, or there is no open update
                  period.
                </p>
              )}

              <div className="act-field-grid">
                <label className="field">
                  <span>Status</span>
                  <select
                    disabled={!canEdit}
                    value={draft.status}
                    onChange={(e) => pickStatus(e.target.value as ActivityStatus)}
                  >
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>% Complete</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    disabled={!canEdit}
                    value={draft.percent_complete}
                    onChange={(e) =>
                      setDraft((d) =>
                        d
                          ? { ...d, percent_complete: Math.max(0, Math.min(100, Number(e.target.value) || 0)) }
                          : d,
                      )
                    }
                  />
                </label>
                <label className="field">
                  <span>Actual Start</span>
                  <input
                    type="date"
                    disabled={!canEdit}
                    value={draft.actual_start ?? ""}
                    onChange={(e) =>
                      setDraft((d) => (d ? { ...d, actual_start: e.target.value || null } : d))
                    }
                  />
                </label>
                <label className="field">
                  <span>Actual Finish</span>
                  <input
                    type="date"
                    disabled={!canEdit}
                    value={draft.actual_finish ?? ""}
                    onChange={(e) =>
                      setDraft((d) => (d ? { ...d, actual_finish: e.target.value || null } : d))
                    }
                  />
                </label>
                <label className="field">
                  <span>Remaining Duration (days)</span>
                  <input
                    type="number"
                    min={0}
                    disabled={!canEdit}
                    value={draft.remaining_duration_days}
                    onChange={(e) =>
                      setDraft((d) =>
                        d ? { ...d, remaining_duration_days: Math.max(0, Number(e.target.value) || 0) } : d,
                      )
                    }
                  />
                </label>
                <div className="field">
                  <span>Important</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={draft.is_important}
                    disabled={!canEdit}
                    className={`gantt-toggle${draft.is_important ? " is-on" : ""}`}
                    style={{ height: 32 }}
                    onClick={() => setDraft((d) => (d ? { ...d, is_important: !d.is_important } : d))}
                  >
                    <span className="gantt-toggle-track">
                      <span className="gantt-toggle-knob" />
                    </span>
                    Flag for attention
                  </button>
                </div>
              </div>

              <div className="field">
                <span>Tags</span>
                <div className="act-tags">
                  {draft.tags.map((t) => (
                    <span key={t} className="act-tag">
                      {t}
                      {canEdit && (
                        <button
                          type="button"
                          aria-label={`Remove ${t}`}
                          onClick={() =>
                            setDraft((d) => (d ? { ...d, tags: d.tags.filter((x) => x !== t) } : d))
                          }
                        >
                          <XIcon className="icon" style={{ width: 10, height: 10 }} />
                        </button>
                      )}
                    </span>
                  ))}
                  {canEdit && (
                    <input
                      type="text"
                      className="act-tag-input"
                      placeholder="Add a tag…"
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addTag();
                        }
                      }}
                      onBlur={addTag}
                    />
                  )}
                </div>
              </div>

              <label className="field">
                <span>Notes</span>
                <textarea
                  rows={3}
                  disabled={!canEdit}
                  placeholder="Why is this activity where it is?"
                  value={draft.notes}
                  onChange={(e) => setDraft((d) => (d ? { ...d, notes: e.target.value } : d))}
                />
              </label>

              {validationError && <p className="act-modal-error">{validationError}</p>}

              {snapshotOnly ? (
                <p className="act-modal-note">
                  You&rsquo;re looking at an earlier programme. Switch to the current update to edit this
                  activity or comment on it.
                </p>
              ) : (
              <div className="act-comments">
                <div className="act-section-label">Comments</div>
                <div className="act-comment-box">
                  <textarea
                    rows={2}
                    placeholder="Add a comment…"
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                  />
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={!commentBody.trim() || posting}
                    onClick={postComment}
                  >
                    {posting ? "Posting…" : "Comment"}
                  </button>
                </div>
                {comments.length === 0 ? (
                  <p className="act-modal-note">No comments yet.</p>
                ) : (
                  <ul className="act-comment-list">
                    {comments.map((c, i) => (
                      <li key={`${c.created_at}-${i}`}>
                        <div className="act-comment-meta">
                          <b>{c.actor_name ?? "Someone"}</b> · {fmtDateTime(c.created_at)}
                        </div>
                        <div>{c.body}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              )}
            </>
          )}

          {/* ---------------- Details ---------------- */}
          {tab === "details" && (
            <div className="act-detail-grid">
              <Detail label="Activity ID" value={activity.external_id} mono />
              <Detail label="Activity Type" value={activity.task_type ?? "—"} />
              <Detail label="P6 Status" value={activity.status_code ?? "—"} />
              <Detail label="WBS" value={wbsName?.wbs_name ?? activity.wbs_path ?? "—"} />
              <Detail label="Discipline" value={activity.discipline} />
              <Detail label="Original Duration" value={days(activity.target_duration_hours)} />
              <Detail label="Remaining Duration" value={days(activity.remaining_duration_hours)} />
              <Detail label="Total Float" value={days(activity.total_float_hours)} />
              <Detail label="Free Float" value={days(activity.free_float_hours)} />
              <Detail label="Critical" value={activity.is_critical ? "Yes" : "No"} />
              <Detail label="On Longest Path" value={activity.is_longest_path ? "Yes" : "No"} />
              <Detail label="% Complete" value={`${activity.percent_complete}%`} />
              <Detail label="Planned Start" value={fmtDate(activity.planned_start)} mono />
              <Detail label="Planned Finish" value={fmtDate(activity.planned_finish)} mono />
              <Detail label="Early Start" value={fmtDate(activity.early_start)} mono />
              <Detail label="Early Finish" value={fmtDate(activity.early_finish)} mono />
              <Detail label="Late Start" value={fmtDate(activity.late_start)} mono />
              <Detail label="Late Finish" value={fmtDate(activity.late_finish)} mono />
              <Detail label="Actual Start" value={fmtDate(activity.actual_start)} mono />
              <Detail label="Actual Finish" value={fmtDate(activity.actual_finish)} mono />
              <Detail
                label="Constraint"
                value={
                  activity.constraint_type
                    ? `${activity.constraint_type} · ${fmtDate(activity.constraint_date)}`
                    : "None"
                }
              />
              <Detail
                label="Secondary Constraint"
                value={
                  activity.constraint_type_2
                    ? `${activity.constraint_type_2} · ${fmtDate(activity.constraint_date_2)}`
                    : "None"
                }
              />
            </div>
          )}

          {/* ---------------- Relationships ---------------- */}
          {tab === "relationships" && (
            <>
              {snapshotOnly ? (
                <p className="act-modal-note">
                  Relationships aren&rsquo;t stored per programme version. Switch to the current update to
                  see this activity&rsquo;s predecessors and successors.
                </p>
              ) : relationships === null ? (
                <p className="act-modal-note">Loading…</p>
              ) : relationships.length === 0 ? (
                <p className="act-modal-note">
                  This activity has no predecessors or successors — an open end in the network.
                </p>
              ) : (
                <>
                  <RelationshipTable
                    title={`Predecessors (${predecessors.length})`}
                    rows={predecessors}
                    otherIdOf={(r) => r.predecessor_external_id}
                  />
                  <RelationshipTable
                    title={`Successors (${successors.length})`}
                    rows={successors}
                    otherIdOf={(r) => r.successor_external_id}
                  />
                </>
              )}
            </>
          )}

          {/* ---------------- History ---------------- */}
          {tab === "history" && (
            <>
              {snapshotOnly ? (
                <p className="act-modal-note">
                  History is kept against the live activity. Switch to the current update to see what
                  changed and who changed it.
                </p>
              ) : history === null ? (
                <p className="act-modal-note">Loading…</p>
              ) : history.length === 0 ? (
                <p className="act-modal-note">
                  Nothing recorded yet. Edits, comments and programme movement all land here.
                </p>
              ) : (
                <ul className="act-timeline">
                  {history.map((h, i) => (
                    <li key={`${h.created_at}-${i}`} className={`act-timeline-item is-${h.kind}`}>
                      <span className="act-timeline-dot">
                        {h.kind === "comment" ? (
                          <FlagIcon className="icon" style={{ width: 11, height: 11 }} />
                        ) : h.kind === "version" ? (
                          <ClockIcon className="icon" style={{ width: 11, height: 11 }} />
                        ) : (
                          <CheckIcon className="icon" style={{ width: 11, height: 11 }} />
                        )}
                      </span>
                      <div style={{ minWidth: 0 }}>
                        {h.kind === "comment" ? (
                          <div>{h.body}</div>
                        ) : (
                          <div>
                            <b>{FIELD_LABELS[h.field ?? ""] ?? h.field}</b>{" "}
                            <span className="mono">{historyValue(h.field, h.old_value)}</span>
                            {" → "}
                            <span className="mono">{historyValue(h.field, h.new_value)}</span>
                          </div>
                        )}
                        <div className="act-timeline-meta">
                          {h.kind === "version"
                            ? `${h.revision_label ?? "Programme"} · ${fmtDateTime(h.created_at)}`
                            : `${h.actor_name ?? "Someone"} · ${fmtDateTime(h.created_at)}`}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        <div className="modal-foot">
          {dirty && <span className="act-modal-dirty">Unsaved changes</span>}
          <button className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
          {canEdit && (
            <button
              className="btn btn-primary"
              disabled={!dirty || saving || Boolean(validationError)}
              onClick={save}
            >
              {saving ? "Saving…" : "Save"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="act-detail">
      <span className="act-detail-label">{label}</span>
      <span className={mono ? "mono" : undefined}>{value}</span>
    </div>
  );
}

function RelationshipTable({
  title,
  rows,
  otherIdOf,
}: {
  title: string;
  rows: ActivityRelationship[];
  otherIdOf: (r: ActivityRelationship) => string | null | undefined;
}) {
  return (
    <div className="act-rel-block">
      <div className="act-section-label">{title}</div>
      {rows.length === 0 ? (
        <p className="act-modal-note">None.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Activity ID</th>
                <th>Type</th>
                <th style={{ textAlign: "right" }}>Lag</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{otherIdOf(r) ?? "—"}</td>
                  <td>{r.link_type}</td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {r.lag_days}d
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
