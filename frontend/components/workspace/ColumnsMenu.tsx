"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDownIcon } from "@/components/icons";
import { COLUMNS, DEFAULT_VISIBLE, type ColKey } from "./columns";

/** "Columns" button + a checklist of the grid's columns. Activity is always
 *  shown; the choice is remembered per browser by the page. */
export function ColumnsMenu({ visible, onChange }: { visible: ColKey[]; onChange: (next: ColKey[]) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle(key: ColKey) {
    const on = visible.includes(key);
    // Keep the canonical column order whatever order they were ticked in.
    const next = COLUMNS.map((c) => c.key).filter((k) => (k === key ? !on : visible.includes(k)));
    onChange(next);
  }

  const isDefault =
    visible.length === DEFAULT_VISIBLE.length && DEFAULT_VISIBLE.every((k) => visible.includes(k));
  const optional = COLUMNS.filter((c) => !c.locked);

  return (
    <div className="qf" ref={ref}>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
      >
        Columns
        <span className="ws-count mono">
          {visible.length - 1}/{optional.length}
        </span>
        <ChevronDownIcon className="icon" style={{ width: 13, height: 13 }} />
      </button>
      {open && (
        <div className="gantt-pop qf-pop is-right" style={{ width: 220 }}>
          <div className="qf-checks">
            {optional.map((c) => {
              const on = visible.includes(c.key);
              return (
                <label key={c.key} className={`qf-check${on ? " is-on" : ""}`}>
                  <input type="checkbox" checked={on} onChange={() => toggle(c.key)} />
                  <span>{c.label}</span>
                </label>
              );
            })}
          </div>
          <div className="qf-foot">
            <span className="qf-foot-note">Activity is always shown</span>
            <button type="button" className="btn btn-ghost btn-sm" disabled={isDefault} onClick={() => onChange(DEFAULT_VISIBLE)}>
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
