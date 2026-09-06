"use client";

import type { ReactNode } from "react";
import type { Activity, WbsNode } from "@/lib/types";
import { buildGridRows, groupByLeaf } from "@/lib/wbs-tree";
import { ChevronDownIcon, ChevronUpIcon } from "@/components/icons";

const INDENT_STEP = 16;
const MAX_INDENT_DEPTH = 4;

function indent(depth: number): number {
  return 8 + Math.min(depth, MAX_INDENT_DEPTH) * INDENT_STEP;
}

export function WbsGrid({
  nodes,
  activities,
  collapsed,
  onToggle,
  colCount,
  header,
  renderActivityCells,
  emptyLabel = "No activities match the current filter.",
}: {
  nodes: WbsNode[];
  activities: Activity[]; // already filtered
  collapsed: Set<string>;
  onToggle: (wbsId: string) => void;
  colCount: number; // number of <td> after the identity cell in an activity row
  header: ReactNode; // <th> cells (identity col + the rest)
  renderActivityCells: (activity: Activity) => ReactNode;
  emptyLabel?: string;
}) {
  const knownWbsIds = new Set(nodes.map((n) => n.wbs_id));
  const byLeaf = groupByLeaf(activities, knownWbsIds);
  const rows = buildGridRows(nodes, byLeaf, collapsed);

  return (
    <div className="table-wrap">
      <table className="progress-grid">
        <thead>
          <tr>{header}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={colCount + 1} className="empty-state">
                {emptyLabel}
              </td>
            </tr>
          )}
          {rows.map((row) => {
            if (row.kind === "band") {
              const d = `d${Math.min(row.depth, 4)}`;
              return (
                <tr key={row.key} className={`wbs-band ${d}`}>
                  <td colSpan={colCount + 1}>
                    <div className="wbs-band-label" style={{ paddingLeft: indent(row.depth) }}>
                      {row.hasChildren ? (
                        <button
                          className="wbs-band-toggle"
                          onClick={() => onToggle(row.wbsId)}
                          aria-label={row.collapsed ? "Expand" : "Collapse"}
                        >
                          {row.collapsed ? (
                            <ChevronDownIcon className="icon" style={{ width: 13, height: 13 }} />
                          ) : (
                            <ChevronUpIcon className="icon" style={{ width: 13, height: 13 }} />
                          )}
                        </button>
                      ) : (
                        <span style={{ width: 13, display: "inline-block" }} />
                      )}
                      <span className="wbs-band-code">{row.outlineCode}</span>
                      <span>{row.label}</span>
                      <span className="wbs-band-roll" style={{ marginLeft: "auto" }}>
                        Σ {row.total}
                        {row.inProgress > 0 ? ` · ${row.inProgress} IP` : ""}
                        {row.completed > 0 ? ` · ${row.completed} done` : ""}
                        {` · ${row.avgPercent}%`}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            }
            const a = row.activity;
            return (
              <tr key={row.key} className={a.is_critical ? "critical" : undefined}>
                <td>
                  <div className="pg-id" style={{ paddingLeft: indent(row.depth) }}>
                    <div className="pg-name">{a.name}</div>
                    {a.external_id}
                  </div>
                </td>
                {renderActivityCells(a)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
