"use client";

import { useState } from "react";
import { ActivityModal } from "@/components/ActivityModal";
import { FlagIcon } from "@/components/icons";
import { floatClass } from "@/components/reporting/format";
import { criticalityChip } from "@/lib/criticality";
import { toDays } from "@/lib/duration";
import { displayFinish, displayStart, finishIsActual, startIsActual } from "@/lib/schedule-dates";
import type { Activity, WbsNode } from "@/lib/types";
import { bandFinishIsActual, bandStartIsActual, fmtUnitsPercent } from "@/lib/wbs-tree";
import { WbsGrid } from "./WbsGrid";

// Status & dates are edited in the Activity modal, not in the grid. The grid's
// job is to be scannable across a few thousand rows; the moment it carries date
// pickers and number inputs in every row it stops being readable, and a stray
// click on the wrong row silently edits the wrong activity. Clicking a row
// opens everything about that activity instead — see components/ActivityModal.

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not Started",
  in_progress: "In Progress",
  complete: "Completed",
};
const STATUS_CHIP: Record<string, string> = {
  not_started: "chip-neutral",
  in_progress: "chip-active",
  complete: "chip-good",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// P6 convention (DD-MMM-YYYY) — see CLAUDE.md.
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

// Total float is stored in hours; shown in the activity's own calendar days
// (lib/duration.ts).
function fmtFloat(a: Activity): string {
  const days = toDays(a.total_float_hours, a);
  if (days === null) return "—";
  return `${days >= 0 ? "" : "-"}${Math.abs(days).toFixed(1)}d`;
}

export function StatusDatesMode({
  hidden,
  nodes,
  activities,
  dataDate,
  canEdit,
  snapshotOnly,
  sortByFloat = false,
  collapsed,
  onToggle,
  onActivitiesUpdated,
}: {
  hidden: boolean;
  nodes: WbsNode[];
  activities: Activity[];
  dataDate: string | null;
  canEdit: boolean;
  snapshotOnly: boolean;
  // "Sort by float" — folded in from the old Planning > Activities view.
  sortByFloat?: boolean;
  collapsed: Set<string>;
  onToggle: (wbsId: string) => void;
  onActivitiesUpdated: (rows: Activity[]) => void;
}) {
  const [openActivity, setOpenActivity] = useState<Activity | null>(null);

  const afterDataDate = (v: string | null | undefined) =>
    Boolean(v && dataDate && v > dataDate.slice(0, 10));

  return (
    <div hidden={hidden}>
      <WbsGrid
        nodes={nodes}
        activities={activities}
        collapsed={collapsed}
        onToggle={onToggle}
        onActivityClick={setOpenActivity}
        sortWithinBand={
          sortByFloat
            ? (a, b) =>
                (toDays(a.total_float_hours, a) ?? Number.POSITIVE_INFINITY) -
                (toDays(b.total_float_hours, b) ?? Number.POSITIVE_INFINITY)
            : undefined
        }
        colCount={7}
        idColumn
        bandCells={{
          labelSpan: 3,
          render: (row) => (
            <>
              <td className="mono">
                {fmtDate(row.spanStart)}
                {bandStartIsActual(row, dataDate) && " A"}
              </td>
              <td className="mono">
                {fmtDate(row.spanFinish)}
                {bandFinishIsActual(row, dataDate) && " A"}
              </td>
              <td />
              <td className="mono" title="Units % complete: Σ actual / Σ budgeted labor hours of the activities shown">
                {fmtUnitsPercent(row)}
              </td>
              <td colSpan={2} />
            </>
          ),
        }}
        header={
          <>
            <th>Activity</th>
            <th style={{ width: 140 }}>Activity ID</th>
            <th>Status</th>
            <th style={{ width: 120 }} title="A = actual date">Start</th>
            <th style={{ width: 120 }} title="A = actual date">Finish</th>
            <th style={{ width: 90 }}>Total Float</th>
            <th style={{ width: 70 }}>%</th>
            <th style={{ width: 90 }} title="Criticality Score (0-100): total float, duration, free float and site risk">
              Criticality
            </th>
            <th style={{ width: 120 }}>Flags</th>
          </>
        }
        renderActivityCells={(a) => {
          const tagCount = a.tags?.length ?? 0;
          return (
            <>
              <td>
                <span className={`chip ${STATUS_CHIP[a.status]}`}>{STATUS_LABEL[a.status]}</span>
              </td>
              <td className="mono">
                {fmtDate(displayStart(a))}
                {startIsActual(a, dataDate) && " A"}
                {a.status !== "not_started" && afterDataDate(a.actual_start) && (
                  <div className="pg-warn">after data date</div>
                )}
              </td>
              <td className="mono">
                {fmtDate(displayFinish(a))}
                {finishIsActual(a, dataDate) && " A"}
                {a.status === "complete" && afterDataDate(a.actual_finish) && (
                  <div className="pg-warn">after data date</div>
                )}
              </td>
              <td className="mono"><span className={floatClass(toDays(a.total_float_hours, a))}>{fmtFloat(a)}</span></td>
              <td className="mono">{a.percent_complete}%</td>
              <td className="mono">
                {a.criticality_score != null ? (
                  <span className={`chip ${criticalityChip(a)}`}>{a.criticality_score}</span>
                ) : (
                  "—"
                )}
              </td>
              <td>
                <div className="pg-flags">
                  {a.is_important && (
                    <span className="chip chip-warn" title="Flagged as important">
                      <FlagIcon className="icon" style={{ width: 10, height: 10 }} />
                    </span>
                  )}
                  {tagCount > 0 && (
                    <span className="chip chip-neutral" title={(a.tags ?? []).join(", ")}>
                      {tagCount} tag{tagCount === 1 ? "" : "s"}
                    </span>
                  )}
                  {a.percent_complete === 100 && !a.actual_finish && (
                    <span className="pg-warn">100% · no finish</span>
                  )}
                </div>
              </td>
            </>
          );
        }}
      />

      <ActivityModal
        key={openActivity?.id ?? "none"}
        activity={openActivity}
        canEdit={canEdit}
        snapshotOnly={snapshotOnly}
        wbsNodes={nodes}
        onClose={() => setOpenActivity(null)}
        onSaved={(updated) => {
          onActivitiesUpdated([updated]);
          setOpenActivity(updated);
        }}
      />
    </div>
  );
}
