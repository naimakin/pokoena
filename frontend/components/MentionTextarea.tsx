"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "@/lib/api";
import type { MentionableUser } from "@/lib/types";

interface Props {
  /** Whose people can be tagged: the activity being commented on. */
  activityId: string;
  value: string;
  onChange: (text: string) => void;
  /** Name → user id for everyone picked from the list (lib/mentions.serializeMentions). */
  picked: Record<string, string>;
  onPickedChange: (picked: Record<string, string>) => void;
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  /** Ctrl/⌘+Enter. */
  onSubmit?: () => void;
  ariaLabel?: string;
}

// "@" at the start of the text or after whitespace, then what's typed so far.
const TRIGGER = /(^|\s)@([^\s@]{0,40})$/;

/** A textarea where typing @ lists the people on this activity; picking one
 *  inserts "@Full Name" and remembers who it was. No library: a listbox
 *  popover under the field, driven by the keyboard (↑ ↓ Enter/Tab Esc). */
export function MentionTextarea({
  activityId,
  value,
  onChange,
  picked,
  onPickedChange,
  placeholder,
  rows = 2,
  disabled,
  onSubmit,
  ariaLabel,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const listId = useId();
  const [query, setQuery] = useState<string | null>(null);
  const [options, setOptions] = useState<MentionableUser[]>([]);
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (query === null) return;
    const timer = window.setTimeout(() => {
      const q = query ? `?q=${encodeURIComponent(query)}` : "";
      api
        .get<MentionableUser[]>(`/activities/${activityId}/mentionable-users${q}`)
        .then((people) => {
          setOptions(people);
          setActive(0);
        })
        .catch(() => setOptions([]));
    }, 150);
    return () => window.clearTimeout(timer);
  }, [query, activityId]);

  function readTrigger(text: string, caret: number) {
    const m = TRIGGER.exec(text.slice(0, caret));
    setQuery(m ? m[2] : null);
  }

  function pick(person: MentionableUser) {
    const el = ref.current;
    if (!el) return;
    const caret = el.selectionStart ?? value.length;
    const before = value.slice(0, caret).replace(TRIGGER, (_all, lead: string) => `${lead}@${person.full_name} `);
    const next = before + value.slice(caret);
    onChange(next);
    onPickedChange({ ...picked, [person.full_name]: person.id });
    setQuery(null);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(before.length, before.length);
    });
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    const open = query !== null && options.length > 0;
    if (open && e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (open && e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + options.length) % options.length);
    } else if (open && (e.key === "Enter" || e.key === "Tab")) {
      e.preventDefault();
      pick(options[active]);
    } else if (query !== null && e.key === "Escape") {
      e.preventDefault();
      setQuery(null);
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && onSubmit) {
      e.preventDefault();
      onSubmit();
    }
  }

  const open = query !== null && options.length > 0;

  return (
    <div className="mention-field">
      <textarea
        ref={ref}
        rows={rows}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={ariaLabel}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        onChange={(e) => {
          onChange(e.target.value);
          readTrigger(e.target.value, e.target.selectionStart ?? e.target.value.length);
        }}
        onKeyDown={onKeyDown}
        onClick={(e) => readTrigger(value, e.currentTarget.selectionStart ?? value.length)}
        onBlur={() => window.setTimeout(() => setQuery(null), 120)}
      />
      {open && (
        <ul className="mention-popover" id={listId} role="listbox" aria-label="People on this activity">
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
                pick(p);
              }}
            >
              <span className="mention-avatar" aria-hidden="true">
                {p.full_name
                  .split(" ")
                  .filter(Boolean)
                  .map((w) => w[0])
                  .slice(0, 2)
                  .join("")
                  .toUpperCase()}
              </span>
              <span className="mention-option-text">
                <span className="mention-option-name">{p.full_name}</span>
                <span className="mention-option-label">{p.label}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
