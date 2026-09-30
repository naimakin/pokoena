"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { WbsNode } from "@/lib/types";
import { ChevronDownIcon } from "@/components/icons";

// The WBS filter as a collapsible tree. A native <select> can only list every
// node flat, which on a real programme is hundreds of rows; here each branch
// folds, so the planner opens only the part of the tree they are after.
export function WbsTreeSelect({
  nodes,
  value,
  onChange,
}: {
  nodes: WbsNode[]; // preorder, as the route returns them
  value: string | null;
  onChange: (wbsId: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const rootRef = useRef<HTMLDivElement>(null);

  const byId = useMemo(() => new Map(nodes.map((n) => [n.wbs_id, n])), [nodes]);
  const hasChildren = useMemo(() => {
    const parents = new Set<string>();
    for (const n of nodes) if (n.parent_wbs_id) parents.add(n.parent_wbs_id);
    return parents;
  }, [nodes]);

  const selected = value ? byId.get(value) ?? null : null;

  // Opening shows the top two levels, plus the way down to the current pick.
  function openPanel() {
    const next = new Set(expanded);
    if (next.size === 0) for (const n of nodes) if (n.depth === 0) next.add(n.wbs_id);
    let cur = selected?.parent_wbs_id ? byId.get(selected.parent_wbs_id) : undefined;
    while (cur) {
      next.add(cur.wbs_id);
      cur = cur.parent_wbs_id ? byId.get(cur.parent_wbs_id) : undefined;
    }
    setExpanded(next);
    setOpen(true);
  }

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // A node shows only while every ancestor is expanded.
  const visible = useMemo(() => {
    const out: WbsNode[] = [];
    let hideBelow: number | null = null;
    for (const n of nodes) {
      if (hideBelow !== null) {
        if (n.depth > hideBelow) continue;
        hideBelow = null;
      }
      out.push(n);
      if (hasChildren.has(n.wbs_id) && !expanded.has(n.wbs_id)) hideBelow = n.depth;
    }
    return out;
  }, [nodes, expanded, hasChildren]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function pick(id: string | null) {
    onChange(id);
    setOpen(false);
  }

  return (
    <div className="wbs-select" ref={rootRef}>
      <button
        type="button"
        className={`wbs-select-trigger${open ? " open" : ""}`}
        aria-haspopup="tree"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openPanel())}
        title={selected ? `${selected.outline_code} ${selected.wbs_name}` : undefined}
      >
        <span className="wbs-select-value">
          {selected ? (
            <>
              <span className="wbs-select-code">{selected.outline_code}</span> {selected.wbs_name}
            </>
          ) : (
            "All WBS"
          )}
        </span>
        <ChevronDownIcon className="icon" style={{ width: 14, height: 14 }} />
      </button>

      {open && (
        <div className="wbs-select-panel" role="tree">
          <div className="wbs-select-tools">
            <button
              type="button"
              className={`wbs-select-all${value === null ? " selected" : ""}`}
              onClick={() => pick(null)}
            >
              All WBS
            </button>
            <span style={{ flex: 1 }} />
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setExpanded(new Set(hasChildren))}
            >
              Expand all
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setExpanded(new Set())}>
              Collapse all
            </button>
          </div>
          <div className="wbs-select-list">
            {visible.map((n) => {
              const branch = hasChildren.has(n.wbs_id);
              const isOpen = expanded.has(n.wbs_id);
              return (
                <div
                  key={n.wbs_id}
                  role="treeitem"
                  aria-expanded={branch ? isOpen : undefined}
                  aria-selected={n.wbs_id === value}
                  className={`wbs-select-row${n.wbs_id === value ? " selected" : ""}`}
                  style={{ paddingLeft: `${0.4 + n.depth * 1}rem` }}
                >
                  {branch ? (
                    <button
                      type="button"
                      className="wbs-select-toggle"
                      aria-label={isOpen ? "Collapse" : "Expand"}
                      onClick={() => toggle(n.wbs_id)}
                    >
                      <ChevronDownIcon
                        className="icon"
                        style={{ width: 13, height: 13, transform: isOpen ? undefined : "rotate(-90deg)" }}
                      />
                    </button>
                  ) : (
                    <span className="wbs-select-toggle" aria-hidden />
                  )}
                  <button type="button" className="wbs-select-label" onClick={() => pick(n.wbs_id)}>
                    <span className="wbs-select-code">{n.outline_code}</span>
                    <span className="wbs-select-name">{n.wbs_name}</span>
                    <span className="wbs-select-count">{n.total_activity_count}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
