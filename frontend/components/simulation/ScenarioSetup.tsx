"use client";

// The scenario being built: the simulation data date and the activities
// changed in it (edited from the programme grid below, Activity Ledger
// style), with the Run bar.

import { ArrowRightIcon, PencilIcon, XIcon } from "@/components/icons";
import { fmtP6Date } from "@/components/reporting/format";
import { isMilestone } from "@/lib/schedule-dates";
import { addDays, addMonths, daysBetween, draftDates, draftSummary, type Draft } from "@/lib/simulation";
import type { Activity } from "@/lib/types";

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

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip ${STATUS_CHIP[status] ?? "chip-neutral"}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export interface Change {
  external_id: string;
  activity: Activity | undefined;
  draft: Draft | null;
  error: string | null;
}

export function ScenarioSetup({
  currentDataDate,
  revisionLabel,
  simDate,
  onSimDate,
  changes,
  dirty,
  onEdit,
  onRemove,
}: {
  currentDataDate: string;
  revisionLabel: string | null;
  simDate: string;
  onSimDate: (d: string) => void;
  changes: Change[];
  dirty: boolean;
  onEdit: (a: Activity) => void;
  onRemove: (externalId: string) => void;
}) {
  const shift = daysBetween(currentDataDate, simDate);
  const dateError = simDate < currentDataDate ? "The simulation data date can't be before the current data date." : null;

  return (
    <div className="card sim-setup">
      <div className="card-head">
        <div>
          <div className="card-title">Scenario</div>
          <div className="card-title-sub">
            Based on the current programme{revisionLabel ? ` (${revisionLabel})` : ""}. Nothing here changes the live schedule.
          </div>
        </div>
        {dirty && <span className="chip chip-warn">Unsaved changes</span>}
      </div>

      <div className="sim-dates">
        <div className="sim-date">
          <span className="sim-date-label">Current data date</span>
          <span className="sim-date-value">{fmtP6Date(currentDataDate)}</span>
        </div>
        <span className="sim-date-arrow" aria-hidden="true">
          <ArrowRightIcon className="icon" />
        </span>
        <div className="sim-date">
          <label className="sim-date-label" htmlFor="sim-data-date">
            Simulation data date
          </label>
          <div className="sim-date-controls">
            <input id="sim-data-date" type="date" value={simDate} min={currentDataDate} onChange={(e) => e.target.value && onSimDate(e.target.value)} />
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSimDate(currentDataDate)}>
              Current
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSimDate(addDays(currentDataDate, 7))}>
              +1 week
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSimDate(addDays(currentDataDate, 14))}>
              +2 weeks
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSimDate(addMonths(currentDataDate, 1))}>
              +1 month
            </button>
          </div>
          {dateError ? (
            <span className="sim-row-error">{dateError}</span>
          ) : (
            <span className="sim-date-note">
              Simulating as of <b>{fmtP6Date(simDate)}</b>
              {shift > 0
                ? `, ${shift} calendar day${shift === 1 ? "" : "s"} after the current data date. Work you don't change stays where it is, so unfinished work slides to the new data date (as P6 does).`
                : ", the current data date."}
            </span>
          )}
        </div>
      </div>

      <div className="sim-changes-head">
        Changed activities <span className="sim-count">{changes.length}</span>
      </div>
      {changes.length === 0 ? (
        <p className="empty-state sim-changes-empty">
          No changes yet. Click an activity in the programme below and edit it as in Activity Workspace — mark it complete,
          change its %, push its finish out — or just move the data date.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="sim-changes">
            <thead>
              <tr>
                <th>Activity</th>
                <th>Activity ID</th>
                <th>Status</th>
                <th className="num">% Complete</th>
                <th>Start</th>
                <th>Finish</th>
                <th>Change</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {changes.map((c) => {
                const a = c.activity;
                const dates = a && c.draft ? draftDates(a, c.draft) : null;
                return (
                  <tr key={c.external_id} className={c.error ? "has-error" : undefined}>
                    <td className="sim-cell-act">
                      {a ? (
                        <button type="button" className="sim-link" onClick={() => onEdit(a)}>
                          {a.name}
                        </button>
                      ) : (
                        <span className="sim-row-error">No longer in the programme</span>
                      )}
                      {c.error && <div className="sim-row-error">{c.error}</div>}
                    </td>
                    <td className="mono sim-cell-id">{c.external_id}</td>
                    <td>{c.draft ? <StatusChip status={c.draft.status} /> : "—"}</td>
                    <td className="num mono">{a && c.draft && !isMilestone(a) ? `${c.draft.percent_complete}%` : "—"}</td>
                    <td className="mono">{fmtP6Date(dates?.start)}</td>
                    <td className="mono">{fmtP6Date(dates?.finish)}</td>
                    <td className="sim-cell-change">{a && c.draft ? draftSummary(a, c.draft) : ""}</td>
                    <td className="sim-cell-remove">
                      <div className="sim-row-actions">
                        {a && (
                          <button type="button" className="act-btn" aria-label={`Edit ${c.external_id}`} title="Edit" onClick={() => onEdit(a)}>
                            <PencilIcon className="icon icon-sm" />
                          </button>
                        )}
                        <button
                          type="button"
                          className="act-btn sim-remove"
                          aria-label={`Remove ${c.external_id} from the scenario`}
                          title="Remove"
                          onClick={() => onRemove(c.external_id)}
                        >
                          <XIcon className="icon icon-sm" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Stays at the bottom of the screen while the programme grid is edited. */
export function RunBar({
  changes,
  shift,
  running,
  canRun,
  onRun,
  onReset,
}: {
  changes: number;
  shift: number;
  running: boolean;
  canRun: boolean;
  onRun: () => void;
  onReset: () => void;
}) {
  return (
    <div className="sim-runbar">
      <span className="sim-runbar-summary">
        {changes === 0 && shift === 0 ? (
          "Edit an activity in the programme or move the data date"
        ) : (
          <>
            <b>
              {changes} change{changes === 1 ? "" : "s"}
            </b>
            {shift > 0 && (
              <>
                {" "}
                · data date <b>+{shift}d</b>
              </>
            )}
          </>
        )}
      </span>
      <button type="button" className="btn btn-ghost" onClick={onReset} disabled={running || (changes === 0 && shift === 0)}>
        Reset
      </button>
      <button type="button" className="btn btn-primary" onClick={onRun} disabled={!canRun || running || shift < 0}>
        {running ? "Simulating…" : "Run simulation"}
        {!running && <span className="sim-kbd">Ctrl ↵</span>}
      </button>
    </div>
  );
}
