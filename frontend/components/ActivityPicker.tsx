"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { XIcon } from "@/components/icons";
import { isMilestone } from "@/lib/schedule-dates";
import type { Activity } from "@/lib/types";

/** Pick one activity by typing part of its ID or name. The value is the P6
 *  activity ID (external_id); "" means none. Milestones list first when
 *  `preferMilestones` is set. */
export function ActivityPicker({
  activities,
  value,
  onChange,
  placeholder = "Search ID or name…",
  preferMilestones = false,
}: {
  activities: Activity[];
  value: string;
  onChange: (externalId: string) => void;
  placeholder?: string;
  preferMilestones?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(() => activities.find((a) => a.external_id === value) ?? null, [activities, value]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = q
      ? activities.filter((a) => a.external_id.toLowerCase().includes(q) || a.name.toLowerCase().includes(q))
      : activities;
    if (preferMilestones) list = [...list].sort((a, b) => Number(isMilestone(b)) - Number(isMilestone(a)));
    return list.slice(0, 12);
  }, [activities, query, preferMilestones]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function pick(a: Activity) {
    onChange(a.external_id);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="act-picker" ref={rootRef}>
      {selected && !open ? (
        <button type="button" className="act-picker-value" onClick={() => setOpen(true)} title={selected.name}>
          <span className="mono">{selected.external_id}</span>
          <span className="act-picker-name">{selected.name}</span>
        </button>
      ) : (
        <input
          value={query}
          autoFocus={open && Boolean(selected)}
          placeholder={value && !selected ? value : placeholder}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setCursor(0);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setCursor((c) => Math.min(c + 1, matches.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setCursor((c) => Math.max(c - 1, 0));
            } else if (e.key === "Enter" && matches[cursor]) {
              e.preventDefault();
              pick(matches[cursor]);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          aria-label={placeholder}
        />
      )}
      {value && (
        <button type="button" className="act-picker-clear" onClick={() => onChange("")} aria-label="Clear">
          <XIcon className="icon" />
        </button>
      )}
      {open && (
        <div className="act-picker-list" role="listbox">
          {matches.length === 0 ? (
            <div className="act-picker-empty">No activity matches.</div>
          ) : (
            matches.map((a, i) => (
              <button
                key={a.id}
                type="button"
                role="option"
                aria-selected={a.external_id === value}
                className={`act-picker-opt${i === cursor ? " is-cursor" : ""}`}
                onMouseEnter={() => setCursor(i)}
                onClick={() => pick(a)}
              >
                <span className="mono">{a.external_id}</span>
                <span className="act-picker-name">{a.name}</span>
                {isMilestone(a) && <span className="chip chip-neutral">Milestone</span>}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
