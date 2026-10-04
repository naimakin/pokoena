"use client";

import { useState, type ReactNode } from "react";
import { fmtDays, fmtP6Date } from "@/components/reporting/format";
import { CheckIcon, LockIcon, TrashIcon } from "@/components/icons";
import type { PersonalNote } from "@/lib/types";

// Private notes and reminders — My Desk's right column and the Activity modal's
// "Private notes" section. Only the author ever sees them (backend
// routes/my_desk.py filters on the caller), which the lock line says out loud.

export interface NoteDraft {
  body: string;
  remind_on: string | null;
}

export interface NotePatch {
  body?: string;
  remind_on?: string | null;
  done?: boolean;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function reminderChip(note: PersonalNote): ReactNode {
  if (!note.remind_on || note.done_at) return null;
  const today = todayIso();
  const due = note.remind_on <= today;
  return (
    <span className={`chip ${due ? "chip-warn" : "chip-neutral"}`}>
      {note.remind_on === today ? "Due today" : due ? `Overdue · ${fmtP6Date(note.remind_on)}` : `Remind ${fmtP6Date(note.remind_on)}`}
    </span>
  );
}

/** "Written at UPD-7: finish 12-Jun-2026, TF +4d" — the activity as it stood. */
function contextLine(note: PersonalNote): string | null {
  const c = note.context;
  if (!c) return null;
  const parts: string[] = [];
  if (c.finish) parts.push(`finish ${fmtP6Date(c.finish)}`);
  if (c.total_float_hours != null) {
    parts.push(`TF ${fmtDays(c.total_float_hours / (c.hours_per_day && c.hours_per_day > 0 ? c.hours_per_day : 8))}`);
  }
  if (!parts.length) return null;
  return `Written at ${c.revision_label ?? "the time"}: ${parts.join(", ")}`;
}

export function NoteComposer({
  placeholder,
  onCreate,
}: {
  placeholder: string;
  onCreate: (draft: NoteDraft) => Promise<boolean>;
}) {
  const [body, setBody] = useState("");
  const [remindOn, setRemindOn] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!body.trim() || saving) return;
    setSaving(true);
    const ok = await onCreate({ body: body.trim(), remind_on: remindOn || null });
    setSaving(false);
    if (ok) {
      setBody("");
      setRemindOn("");
    }
  }

  return (
    <div className="note-composer">
      <textarea
        rows={2}
        placeholder={placeholder}
        value={body}
        maxLength={4000}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="note-composer-row">
        <span className="note-private">
          <LockIcon className="icon icon-xs" /> Only you can see this
        </span>
        <label className="note-remind">
          Remind me
          <input type="date" value={remindOn} onChange={(e) => setRemindOn(e.target.value)} />
        </label>
        <button className="btn btn-primary btn-sm" disabled={!body.trim() || saving} onClick={submit}>
          {saving ? "Saving…" : "Add note"}
        </button>
      </div>
    </div>
  );
}

function NoteItem({
  note,
  showProject,
  showActivity,
  onOpenActivity,
  onUpdate,
  onDelete,
}: {
  note: PersonalNote;
  showProject: boolean;
  showActivity: boolean;
  /** Returns undefined when this note's activity can't be opened from here. */
  onOpenActivity?: (note: PersonalNote) => (() => void) | undefined;
  onUpdate: (id: string, patch: NotePatch) => Promise<boolean>;
  onDelete: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(note.body);
  const done = Boolean(note.done_at);
  const context = contextLine(note);
  const open = onOpenActivity?.(note);

  async function commit() {
    const next = text.trim();
    setEditing(false);
    if (!next) {
      setText(note.body);
      return;
    }
    if (next !== note.body && !(await onUpdate(note.id, { body: next }))) setText(note.body);
  }

  return (
    <li className={`note-item${done ? " is-done" : ""}`}>
      <button
        type="button"
        className={`note-check${done ? " is-on" : ""}`}
        role="checkbox"
        aria-checked={done}
        aria-label={done ? "Mark as open" : "Mark as done"}
        title={done ? "Mark as open" : "Mark as done"}
        onClick={() => onUpdate(note.id, { done: !done })}
      >
        {done && <CheckIcon className="icon" />}
      </button>
      <div className="note-main">
        {editing ? (
          <textarea
            autoFocus
            rows={Math.min(8, Math.max(2, text.split("\n").length))}
            value={text}
            maxLength={4000}
            onChange={(e) => setText(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.stopPropagation();
                setText(note.body);
                setEditing(false);
              }
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                commit();
              }
            }}
          />
        ) : (
          <button type="button" className="note-body" title="Click to edit" onClick={() => setEditing(true)}>
            {note.body}
          </button>
        )}
        <div className="note-meta">
          {showProject && note.project_code && <span className="chip chip-neutral mono">{note.project_code}</span>}
          {showProject && !note.project_id && <span className="chip chip-neutral">General</span>}
          {showActivity && note.activity_external_id && (
            open ? (
              <button type="button" className="note-activity" onClick={open} title={note.activity_name ?? undefined}>
                <span className="mono">{note.activity_external_id}</span> {note.activity_name}
              </button>
            ) : (
              <span className="note-activity-static" title={note.activity_name ?? undefined}>
                <span className="mono">{note.activity_external_id}</span> {note.activity_name}
              </span>
            )
          )}
          {reminderChip(note)}
          <span className="note-date mono">{fmtP6Date(note.created_at)}</span>
        </div>
        {context && <div className="note-context">{context}</div>}
      </div>
      <button
        type="button"
        className="btn btn-ghost btn-sm note-delete"
        aria-label="Delete note"
        title="Delete note"
        onClick={() => onDelete(note.id)}
      >
        <TrashIcon className="icon icon-sm" />
      </button>
    </li>
  );
}

export function NoteList({
  notes,
  showProject = false,
  showActivity = true,
  emptyText,
  onOpenActivity,
  onUpdate,
  onDelete,
}: {
  notes: PersonalNote[];
  showProject?: boolean;
  showActivity?: boolean;
  emptyText: string;
  onOpenActivity?: (note: PersonalNote) => (() => void) | undefined;
  onUpdate: (id: string, patch: NotePatch) => Promise<boolean>;
  onDelete: (id: string) => void;
}) {
  const [showDone, setShowDone] = useState(false);
  const openNotes = notes.filter((n) => !n.done_at);
  const done = notes.filter((n) => n.done_at);
  const item = (n: PersonalNote) => (
    <NoteItem
      key={`${n.id}-${n.updated_at}`}
      note={n}
      showProject={showProject}
      showActivity={showActivity}
      onOpenActivity={onOpenActivity}
      onUpdate={onUpdate}
      onDelete={onDelete}
    />
  );

  return (
    <>
      {openNotes.length === 0 ? <p className="note-empty">{emptyText}</p> : <ul className="note-list">{openNotes.map(item)}</ul>}
      {done.length > 0 && (
        <>
          <button type="button" className="note-done-toggle" onClick={() => setShowDone((v) => !v)}>
            {showDone ? "Hide done" : `Done (${done.length})`}
          </button>
          {showDone && <ul className="note-list">{done.map(item)}</ul>}
        </>
      )}
    </>
  );
}
