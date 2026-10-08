"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "@/lib/api";
import type { MentionableUser } from "@/lib/types";

export type OwnerChange = { owner_user_id: string } | { owner_name: string | null };

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

/** An action's owner: a person who can see the activity, picked from a list
 *  (type @ or just a name), shown as a chip. Free text still works for someone
 *  outside POKO, and older plans keep their typed owner. */
export function OwnerPicker({
  peopleUrl,
  ownerId,
  ownerName,
  editable,
  onChange,
}: {
  /** GET → MentionableUser[] (takes q, include_self). */
  peopleUrl: string;
  ownerId: string | null;
  ownerName: string | null;
  editable: boolean;
  onChange: (change: OwnerChange) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<MentionableUser[]>([]);
  const [active, setActive] = useState(0);
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);

  const needle = query.replace(/^@/, "").trim();

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      const q = needle ? `&q=${encodeURIComponent(needle)}` : "";
      api
        .get<MentionableUser[]>(`${peopleUrl}?include_self=true${q}`)
        .then((people) => {
          setOptions(people);
          setActive(0);
        })
        .catch(() => setOptions([]));
    }, 120);
    return () => window.clearTimeout(timer);
  }, [open, needle, peopleUrl]);

  // Close on a click outside.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // Rows in the list: people, then "use as a name" for free text, then clear.
  const freeText = needle && !options.some((p) => p.full_name.toLowerCase() === needle.toLowerCase()) ? needle : null;
  const extra = (freeText ? 1 : 0) + (ownerName ? 1 : 0);
  const total = options.length + extra;

  function choose(index: number) {
    if (index < options.length) onChange({ owner_user_id: options[index].id });
    else if (freeText && index === options.length) onChange({ owner_name: freeText });
    else onChange({ owner_name: null });
    setOpen(false);
    setQuery("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" && total) {
      e.preventDefault();
      setActive((i) => (i + 1) % total);
    } else if (e.key === "ArrowUp" && total) {
      e.preventDefault();
      setActive((i) => (i - 1 + total) % total);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (total) choose(active);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      setQuery("");
    }
  }

  const chip = ownerName ? (
    <span className={`rp-owner${ownerId ? " is-person" : ""}`} title={ownerId ? ownerName : `${ownerName} (typed name)`}>
      {ownerId && (
        <span className="rp-owner-avatar" aria-hidden="true">
          {initials(ownerName)}
        </span>
      )}
      <span className="rp-owner-name">{ownerName}</span>
    </span>
  ) : (
    <span className="rp-owner is-empty">{editable ? "Assign owner" : "No owner"}</span>
  );

  if (!editable) return chip;

  return (
    <div className="rp-owner-picker" ref={rootRef}>
      {open ? (
        <input
          type="text"
          autoFocus
          className="rp-owner-input"
          value={query}
          placeholder="@ name"
          role="combobox"
          aria-label="Owner"
          aria-expanded={total > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={total ? `${listId}-${active}` : undefined}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />
      ) : (
        <button type="button" className="rp-owner-btn" onClick={() => setOpen(true)} aria-label={ownerName ? `Owner: ${ownerName}. Change` : "Assign owner"}>
          {chip}
        </button>
      )}
      {open && total > 0 && (
        <ul className="mention-popover rp-owner-popover" id={listId} role="listbox" aria-label="People on this activity">
          {options.map((p, i) => (
            <li
              key={p.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={`mention-option${i === active ? " is-active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(i);
              }}
            >
              <span className="mention-avatar" aria-hidden="true">
                {initials(p.full_name)}
              </span>
              <span className="mention-option-text">
                <span className="mention-option-name">
                  {p.full_name}
                  {p.id === ownerId ? " · owner" : ""}
                </span>
                <span className="mention-option-label">{p.label}</span>
              </span>
            </li>
          ))}
          {freeText && (
            <li
              id={`${listId}-${options.length}`}
              role="option"
              aria-selected={active === options.length}
              className={`mention-option rp-owner-extra${active === options.length ? " is-active" : ""}`}
              onMouseEnter={() => setActive(options.length)}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(options.length);
              }}
            >
              Use &ldquo;{freeText}&rdquo; as a name
            </li>
          )}
          {ownerName && (
            <li
              id={`${listId}-${total - 1}`}
              role="option"
              aria-selected={active === total - 1}
              className={`mention-option rp-owner-extra${active === total - 1 ? " is-active" : ""}`}
              onMouseEnter={() => setActive(total - 1)}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(total - 1);
              }}
            >
              Clear owner
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
