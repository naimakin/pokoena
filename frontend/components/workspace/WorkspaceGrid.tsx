"use client";

import type { KeyboardEvent, MouseEvent as ReactMouseEvent } from "react";
import { ChevronDownIcon } from "@/components/icons";
import type { Activity } from "@/lib/types";
import type { GridRow } from "@/lib/wbs-tree";
import type { CellCtx, ColKey, ColumnDef } from "./columns";
import { ROW_H } from "./model";

// The left-hand grid of Activity Workspace: div rows of a fixed height, so the
// Gantt beside it can line up row for row (a <table> can't promise that).

export function GridHead({
  columns,
  widths,
  height,
  onResizeStart,
}: {
  columns: ColumnDef[];
  widths: Record<ColKey, number>;
  height: number;
  onResizeStart: (e: ReactMouseEvent, key: ColKey) => void;
}) {
  return (
    <div className="gantt-head" style={{ height }}>
      {columns.map((c) => (
        <div
          key={c.key}
          className={`gantt-head-cell${c.align === "right" ? " is-num" : ""}`}
          style={{ width: widths[c.key] }}
          title={c.title}
        >
          <span>{c.label}</span>
          <span
            className="gantt-col-resizer"
            onMouseDown={(e) => onResizeStart(e, c.key)}
            role="separator"
            aria-label={`Resize ${c.label} column`}
          />
        </div>
      ))}
    </div>
  );
}

export function GridRowCells({
  row,
  idx,
  columns,
  widths,
  ctx,
  onToggleBand,
  onActivityClick,
}: {
  row: GridRow;
  idx: number;
  columns: ColumnDef[];
  widths: Record<ColKey, number>;
  ctx: CellCtx;
  onToggleBand: (wbsId: string) => void;
  onActivityClick: (a: Activity) => void;
}) {
  if (row.kind === "band") {
    // The WBS label takes Activity plus the identity columns right after it
    // (ID, Status), so its name and "N activities · M completed" have room.
    let labelW = widths[columns[0].key];
    let i = 1;
    while (i < columns.length && columns[i].mergeIntoLabel) {
      labelW += widths[columns[i].key];
      i += 1;
    }
    const rest = columns.slice(i);
    return (
      <div className={`gantt-row is-band d${Math.min(row.depth, 4)}`} style={{ height: ROW_H }}>
        <div className="gantt-cell ws-band-cell" style={{ width: labelW }}>
          <span className="ws-band-label" style={{ paddingLeft: row.depth * 12 }}>
            {row.hasChildren ? (
              <button
                type="button"
                className="gantt-caret"
                onClick={() => onToggleBand(row.wbsId)}
                aria-label={row.collapsed ? `Expand ${row.label}` : `Collapse ${row.label}`}
                aria-expanded={!row.collapsed}
                style={{ transform: row.collapsed ? "rotate(-90deg)" : "none" }}
              >
                <ChevronDownIcon className="icon" style={{ width: 13, height: 13 }} />
              </button>
            ) : (
              <span style={{ width: 13, flexShrink: 0 }} />
            )}
            <span className="ws-band-code mono">{row.outlineCode}</span>
            <span className="gantt-cell-text" title={`${row.outlineCode} ${row.label}`}>
              {row.label}
            </span>
            <span className="ws-band-roll mono">
              {row.total} {row.total === 1 ? "activity" : "activities"} · {row.completed} completed
            </span>
          </span>
        </div>
        {rest.map((c) => (
          <div
            key={c.key}
           
            className={`gantt-cell${c.align === "right" ? " is-num" : ""}`}
            style={{ width: widths[c.key] }}
          >
            {c.band?.(row, ctx)}
          </div>
        ))}
      </div>
    );
  }

  const a = row.activity;
  // Finished work is never "critical" regardless of its stored float — P6's
  // own convention (see services/xer_import.py::_is_critical).
  const isFinished = a.status === "complete" || Boolean(a.actual_finish);
  const critical = !isFinished && a.is_critical;
  const open = () => onActivityClick(a);
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  };

  return (
    <div
      className={`gantt-row is-open${idx % 2 === 0 ? "" : " is-odd"}${critical ? " is-critical" : ""}`}
      style={{ height: ROW_H }}
      role="button"
      tabIndex={0}
      aria-label={`${a.external_id} ${a.name} — open activity`}
      onClick={open}
      onKeyDown={onKeyDown}
    >
      {columns.map((c, ci) => (
        <div
          key={c.key}
          className={`gantt-cell${c.align === "right" ? " is-num" : ""}`}
          style={{ width: widths[c.key], paddingLeft: ci === 0 ? row.depth * 12 + 25 : undefined }}
        >
          {c.activity(a, ctx)}
        </div>
      ))}
    </div>
  );
}
