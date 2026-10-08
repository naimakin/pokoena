"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { MentionText } from "@/components/MentionText";
import { MentionTextarea } from "@/components/MentionTextarea";
import { fmtP6Date } from "@/components/reporting/format";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon, PencilIcon, TrashIcon } from "@/components/icons";
import { mentionEditable, serializeMentions } from "@/lib/mentions";
import type { RecoveryItemStatusValue, RecoveryPlan, RecoveryPlanItem } from "@/lib/types";
import { OwnerPicker, type OwnerChange } from "./OwnerPicker";

// The plan behind one slipped activity on Programme › Recovery Plan (and the
// subcontractor's own Recovery Plans page). Everything the author wrote stays
// editable in every status — editing never changes the status; the backend
// records who edited it and when, and the panel says so once the plan has been
// submitted or acknowledged (routes/recovery_plans.py).

const ITEM_STATUS: { value: RecoveryItemStatusValue; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
  { value: "dropped", label: "Dropped" },
];

type SaveState = "idle" | "saving" | "saved" | "error";

function Step({ state, label, detail }: { state: "done" | "current" | "todo" | "back"; label: string; detail?: string | null }) {
  return (
    <li className={`rp-step is-${state}`}>
      <span className="rp-step-dot" aria-hidden="true">
        {state === "done" ? <CheckIcon className="icon" /> : null}
      </span>
      <span className="rp-step-text">
        <span className="rp-step-label">{label}</span>
        {detail && <span className="rp-step-detail">{detail}</span>}
      </span>
    </li>
  );
}

function who(name: string | null | undefined, iso: string | null | undefined): string | null {
  const parts = [name, iso ? fmtP6Date(iso) : null].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

/** Draft → Submitted → Acknowledged, with who and when. A plan sent back shows
 *  "Needs revision" in the last step instead. */
function Timeline({ plan }: { plan: RecoveryPlan }) {
  const s = plan.status;
  const submitted = s === "submitted" || s === "accepted" || (s === "needs_revision" && !!plan.submitted_at);
  return (
    <ol className="rp-timeline" aria-label="Plan status">
      <Step state={s === "draft" ? "current" : "done"} label="Draft" detail={who(plan.author_name, plan.created_at)} />
      <Step
        state={s === "submitted" ? "current" : submitted ? "done" : "todo"}
        label="Submitted"
        detail={submitted ? who(plan.submitted_by_name, plan.submitted_at) : null}
      />
      {s === "needs_revision" ? (
        <Step state="back" label="Needs revision" detail={who(plan.reviewed_by_name, plan.reviewed_at)} />
      ) : (
        <Step
          state={s === "accepted" ? "done" : "todo"}
          label="Acknowledged"
          detail={s === "accepted" ? who(plan.reviewed_by_name, plan.reviewed_at) : null}
        />
      )}
    </ol>
  );
}

function SaveNote({ state }: { state: SaveState }) {
  return (
    <span className={`rp-save is-${state}`} aria-live="polite">
      {state === "saving" ? (
        "Saving…"
      ) : state === "saved" ? (
        <>
          <CheckIcon className="icon" /> Saved
        </>
      ) : state === "error" ? (
        "Not saved"
      ) : null}
    </span>
  );
}

/** Text with @mentions: shown as text, edited in place (Edit → Save / Cancel). */
function MentionField({
  value,
  peopleUrl,
  editing,
  onEditingChange,
  onSave,
  placeholder,
  ariaLabel,
  rows = 3,
  empty,
}: {
  value: string | null;
  peopleUrl: string;
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  onSave: (body: string) => Promise<boolean>;
  placeholder: string;
  ariaLabel: string;
  rows?: number;
  empty: ReactNode;
}) {
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!editing) return;
    const e = mentionEditable(value);
    setText(e.text);
    setPicked(e.picked);
  }, [editing, value]);

  async function save() {
    if (busy) return;
    setBusy(true);
    const ok = await onSave(serializeMentions(text.trim(), picked));
    setBusy(false);
    if (ok) onEditingChange(false);
  }

  if (!editing) {
    return value ? (
      <p className="rp-text">
        <MentionText body={value} />
      </p>
    ) : (
      <>{empty}</>
    );
  }
  return (
    <div className="rp-edit">
      <MentionTextarea
        peopleUrl={peopleUrl}
        value={text}
        onChange={setText}
        picked={picked}
        onPickedChange={setPicked}
        placeholder={placeholder}
        ariaLabel={ariaLabel}
        rows={rows}
        autoFocus
        onSubmit={save}
        onCancel={() => onEditingChange(false)}
      />
      <div className="rp-edit-actions">
        <button type="button" className="btn btn-primary btn-sm" onClick={save} disabled={busy}>
          Save
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onEditingChange(false)} disabled={busy}>
          Cancel
        </button>
        <span className="rp-hint">Type @ to mention someone · Ctrl+Enter saves</span>
      </div>
    </div>
  );
}

export function RecoveryPlanPanel({
  projectId,
  plan,
  context,
  canTrack,
  canAcknowledge,
  adminReview = false,
  meId,
  onChanged,
}: {
  projectId: string;
  plan: RecoveryPlan;
  /** One quiet line about the activity (status, %, WBS). */
  context?: ReactNode;
  /** May tick action progress once acknowledged, without being the author. */
  canTrack: boolean;
  /** Manages progress: may acknowledge / send back someone else's plan. */
  canAcknowledge: boolean;
  /** Company admins may acknowledge a plan they wrote themselves. */
  adminReview?: boolean;
  meId: string | null;
  /** Reload the plan (and the slip report when the status moved). */
  onChanged: (statusMoved: boolean) => Promise<void> | void;
}) {
  const { showToast } = useToast();
  const base = `/projects/${projectId}/recovery-plan/plans/${plan.id}`;
  const peopleUrl = `${base}/people`;
  const items = plan.items ?? [];
  const editable = plan.can_edit;
  const trackable = editable || (canTrack && plan.status === "accepted");

  const [save, setSave] = useState<SaveState>("idle");
  const [editingRoot, setEditingRoot] = useState(false);
  const [editingItem, setEditingItem] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [draftPicked, setDraftPicked] = useState<Record<string, string>>({});
  const [reviewing, setReviewing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const savedTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (savedTimer.current) window.clearTimeout(savedTimer.current);
  }, []);

  async function run(fn: () => Promise<unknown>, statusMoved = false): Promise<boolean> {
    setSave("saving");
    try {
      await fn();
      await onChanged(statusMoved);
      setSave("saved");
      if (savedTimer.current) window.clearTimeout(savedTimer.current);
      savedTimer.current = window.setTimeout(() => setSave("idle"), 2200);
      return true;
    } catch (err) {
      setSave("error");
      showToast(err instanceof ApiError ? err.message : "Could not save.", "error");
      return false;
    }
  }

  const patchItem = (id: string, body: Record<string, unknown>) => run(() => api.patch(`${base}/items/${id}`, body));

  function setOwner(item: RecoveryPlanItem, change: OwnerChange) {
    if ("owner_user_id" in change && change.owner_user_id === item.owner_user_id) return;
    patchItem(item.id, change);
  }

  function setStatus(item: RecoveryPlanItem, status: RecoveryItemStatusValue) {
    if (status === item.status) return;
    patchItem(item.id, { status, completed_at: status === "done" ? new Date().toISOString().slice(0, 10) : null });
  }

  function move(idx: number, dir: -1 | 1) {
    const next = [...items];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    run(() => api.put(`${base}/items/order`, { ordered_item_ids: next.map((i) => i.id) }));
  }

  function remove(item: RecoveryPlanItem) {
    if (!window.confirm("Remove this action?")) return;
    run(() => api.delete(`${base}/items/${item.id}`));
  }

  async function addAction() {
    const action = serializeMentions(draft.trim(), draftPicked);
    if (!action || busy) return;
    setBusy(true);
    const ok = await run(() => api.post(`${base}/items`, { action }));
    setBusy(false);
    if (ok) {
      setDraft("");
      setDraftPicked({});
    }
  }

  async function act(path: string, body?: unknown) {
    setBusy(true);
    const ok = await run(() => api.post(`${base}${path}`, body), true);
    setBusy(false);
    if (ok) {
      setReviewing(false);
      setNote("");
    }
  }

  const wrote = meId !== null && (plan.created_by_user_id === meId || plan.submitted_by_user_id === meId);
  const submittable = editable && (plan.status === "draft" || plan.status === "needs_revision");
  const canReview = canAcknowledge && plan.status === "submitted" && (!wrote || adminReview);
  const raisedOn = plan.from_label && plan.to_label ? `${plan.from_label} → ${plan.to_label}` : null;

  return (
    <div className="rp-panel">
      <div className="rp-panel-head">
        <div className="rp-context">
          {context}
          {raisedOn && <span>Raised on {raisedOn}</span>}
          {plan.revision_no > 1 && <span>Revision {plan.revision_no}</span>}
          {plan.scope_name && <span>{plan.scope_name}</span>}
        </div>
        <Timeline plan={plan} />
      </div>

      {plan.edited_after && (
        <div className={`rp-edited is-${plan.edited_after}`} role="note">
          <PencilIcon className="icon" />
          Edited after {plan.edited_after}
          {plan.edited_at ? ` · ${fmtP6Date(plan.edited_at)}` : ""}
          {plan.edited_by_name ? ` · ${plan.edited_by_name}` : ""}
        </div>
      )}
      {plan.status === "needs_revision" && plan.review_note && (
        <div className="banner warn">
          <span className="banner-text">
            <b>Sent back{plan.reviewed_by_name ? ` by ${plan.reviewed_by_name}` : ""}:</b> {plan.review_note}
          </span>
        </div>
      )}

      <section className="rp-block" aria-label="Root cause">
        <div className="rp-block-head">
          <span className="rp-label">Root cause</span>
          {editable && !editingRoot && (
            <button type="button" className="btn btn-ghost btn-sm no-print" onClick={() => setEditingRoot(true)}>
              <PencilIcon className="icon" /> {plan.summary ? "Edit" : "Add"}
            </button>
          )}
        </div>
        <MentionField
          value={plan.summary}
          peopleUrl={peopleUrl}
          editing={editingRoot}
          onEditingChange={setEditingRoot}
          onSave={(summary) => run(() => api.patch(base, { summary: summary || null }))}
          placeholder="Why did it slip? What's driving the delay?"
          ariaLabel="Root cause"
          empty={
            <p className="rp-empty">
              {editable ? "Not written yet. Say why the activity slipped." : "No root cause given yet."}
            </p>
          }
        />
      </section>

      <section className="rp-block" aria-label="Recovery actions">
        <div className="rp-block-head">
          <span className="rp-label">
            Recovery actions <span className="rp-count">{items.length}</span>
          </span>
          <SaveNote state={save} />
        </div>

        {items.length === 0 ? (
          <p className="rp-empty">
            {editable ? "No actions yet. Add the first one below; a plan needs at least one to submit." : "No actions yet."}
          </p>
        ) : (
          <ol className="rp-actions">
            {items.map((item, idx) => (
              <li key={item.id} className={`rp-action is-${item.status}`}>
                <span className="rp-action-no num">{idx + 1}</span>
                <div className="rp-action-main">
                  {editingItem === item.id ? (
                    <MentionField
                      value={item.action}
                      peopleUrl={peopleUrl}
                      editing
                      onEditingChange={(on) => setEditingItem(on ? item.id : null)}
                      onSave={(action) => (action ? patchItem(item.id, { action }) : Promise.resolve(false))}
                      placeholder="What will be done?"
                      ariaLabel="Action"
                      rows={2}
                      empty={null}
                    />
                  ) : editable ? (
                    <button
                      type="button"
                      className="rp-action-text is-editable"
                      onClick={() => setEditingItem(item.id)}
                      title="Edit action"
                    >
                      <MentionText body={item.action} />
                    </button>
                  ) : (
                    <span className="rp-action-text">
                      <MentionText body={item.action} />
                    </span>
                  )}
                  <div className="rp-action-meta">
                    <OwnerPicker
                      peopleUrl={peopleUrl}
                      ownerId={item.owner_user_id}
                      ownerName={item.owner_name}
                      editable={editable}
                      onChange={(change) => setOwner(item, change)}
                    />
                    {editable ? (
                      <label className="rp-date">
                        <span>Target</span>
                        <input
                          type="date"
                          defaultValue={item.target_date ?? ""}
                          key={`${item.id}-${item.target_date ?? ""}`}
                          onBlur={(e) =>
                            e.target.value !== (item.target_date ?? "") &&
                            patchItem(item.id, { target_date: e.target.value || null })
                          }
                        />
                      </label>
                    ) : (
                      <span className="rp-date num">{item.target_date ? `Target ${fmtP6Date(item.target_date)}` : "No target date"}</span>
                    )}
                  </div>
                </div>
                <div className="rp-action-side">
                  {trackable ? (
                    <select
                      className={`rp-status is-${item.status}`}
                      value={item.status}
                      aria-label="Action status"
                      onChange={(e) => setStatus(item, e.target.value as RecoveryItemStatusValue)}
                    >
                      {ITEM_STATUS.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className={`rp-status is-${item.status}`}>
                      {ITEM_STATUS.find((s) => s.value === item.status)?.label}
                    </span>
                  )}
                  {editable && (
                    <span className="rp-action-tools no-print">
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => move(idx, -1)} disabled={idx === 0} aria-label="Move up" title="Move up">
                        <ChevronUpIcon className="icon" />
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => move(idx, 1)}
                        disabled={idx === items.length - 1}
                        aria-label="Move down"
                        title="Move down"
                      >
                        <ChevronDownIcon className="icon" />
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove(item)} aria-label="Remove action" title="Remove">
                        <TrashIcon className="icon" />
                      </button>
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}

        {editable && (
          <div className="rp-add no-print">
            <MentionTextarea
              peopleUrl={peopleUrl}
              value={draft}
              onChange={setDraft}
              picked={draftPicked}
              onPickedChange={setDraftPicked}
              placeholder="Add an action… (type @ to mention someone)"
              ariaLabel="New action"
              rows={1}
              onSubmit={addAction}
            />
            <button type="button" className="btn btn-secondary btn-sm" onClick={addAction} disabled={busy || !draft.trim()}>
              Add action
            </button>
          </div>
        )}
      </section>

      {(submittable || canReview || (plan.status === "submitted" && wrote)) && (
        <div className="rp-footer no-print">
          {submittable && (
            <>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => act("/submit")}
                disabled={busy || items.length === 0}
              >
                {plan.status === "needs_revision" ? "Resubmit plan" : "Submit plan"}
              </button>
              {items.length === 0 && <span className="rp-hint">Add at least one action to submit.</span>}
            </>
          )}
          {canReview && !reviewing && (
            <>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => act("/review", { decision: "accept" })} disabled={busy}>
                <CheckIcon className="icon" /> Acknowledge
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReviewing(true)} disabled={busy}>
                Needs revision
              </button>
            </>
          )}
          {canReview && reviewing && (
            <div className="rp-review">
              <textarea
                rows={2}
                autoFocus
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="What should change? The author sees this note."
                aria-label="Revision note"
              />
              <div className="rp-edit-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => act("/review", { decision: "needs_revision", note: note.trim() || null })}
                  disabled={busy}
                >
                  Send back
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setReviewing(false)} disabled={busy}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          {plan.status === "submitted" && wrote && !canReview && (
            <span className="rp-hint">Waiting for someone else on the team to acknowledge it.</span>
          )}
        </div>
      )}
    </div>
  );
}
