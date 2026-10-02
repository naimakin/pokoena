"use client";

// The scenario being built: the simulation data date, the changed activities
// (each with one change), and the search box that adds them.

import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ArrowRightIcon, XIcon } from "@/components/icons";
import { FloatBadge, fmtP6Date } from "@/components/reporting/format";
import {
  addDays,
  addMonths,
  DATE_KINDS,
  daysBetween,
  kindLabel,
  kindOptions,
  valueForKind,
  type SimContextActivity,
  type SimEdit,
  type SimEditKind,
} from "@/lib/simulation";

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

// --- activity picker (ARIA combobox) ------------------------------------------------

function ActivityPicker({
  activities,
  inScenario,
  onPick,
}: {
  activities: SimContextActivity[];
  inScenario: Set<string>;
  onPick: (a: SimContextActivity) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const scored: { a: SimContextActivity; rank: number }[] = [];
    for (const a of activities) {
      const id = a.external_id.toLowerCase();
      const rank = id === q ? 0 : id.startsWith(q) ? 1 : id.includes(q) ? 2 : q.length >= 2 && a.name.toLowerCase().includes(q) ? 3 : -1;
      if (rank >= 0) scored.push({ a, rank });
    }
    scored.sort((x, y) => x.rank - y.rank || x.a.external_id.localeCompare(y.a.external_id));
    return scored.slice(0, 12).map((s) => s.a);
  }, [activities, query]);

  const selectable = (a: SimContextActivity) => a.status !== "complete" && !inScenario.has(a.external_id);

  function pick(a: SimContextActivity | undefined) {
    if (!a || !selectable(a)) return;
    onPick(a);
    setQuery("");
    setActive(0);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(matches.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      if (open && matches[active]) {
        e.preventDefault();
        pick(matches[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && query.trim().length > 0;
  return (
    <div className="sim-picker">
      <input
        type="text"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && matches[active] ? `${listId}-${active}` : undefined}
        aria-label="Add an activity to the scenario"
        placeholder="Add an activity: search ID or name"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <div className="sim-picker-list" role="listbox" id={listId}>
          {matches.length === 0 && <div className="sim-picker-empty">No activity matches “{query.trim()}”.</div>}
          {matches.map((a, i) => {
            const disabled = !selectable(a);
            return (
              <div
                key={a.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                aria-disabled={disabled}
                className="sim-picker-opt"
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(a);
                }}
              >
                <span className="sim-picker-id">{a.external_id}</span>
                <span className="sim-picker-name">{a.name}</span>
                {a.status === "complete" ? (
                  <span className="chip chip-good">Completed</span>
                ) : inScenario.has(a.external_id) ? (
                  <span className="chip chip-info">In scenario</span>
                ) : (
                  <StatusChip status={a.status} />
                )}
                <span className="sim-picker-date">{fmtP6Date(a.finish ?? a.start)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- one change ------------------------------------------------------------------

function ChangeEditor({
  activity,
  edit,
  simDate,
  error,
  onChange,
}: {
  activity: SimContextActivity;
  edit: SimEdit;
  simDate: string;
  error: string | null;
  onChange: (e: SimEdit) => void;
}) {
  const id = activity.external_id;
  const kinds = kindOptions(activity);
  const milestone = activity.is_milestone;
  const num = typeof edit.value === "number" ? edit.value : "";
  const dateValue = typeof edit.value === "string" ? edit.value : "";

  function setKind(kind: SimEditKind) {
    onChange({ external_id: id, kind, value: valueForKind(kind, activity, simDate), actual_start: null });
  }
  function setNumber(raw: string) {
    onChange({ ...edit, value: raw === "" ? Number.NaN : Number(raw) });
  }

  // "Finish later by N working days" lands roughly here — the server works
  // out the exact date on the activity's own calendar.
  const delayHint =
    edit.kind === "finish_delay" && typeof edit.value === "number" && activity.finish
      ? addDays(activity.finish, Math.round((edit.value * 7) / 5))
      : null;

  return (
    <div className="sim-edit">
      <select className="select-sm" value={edit.kind} onChange={(e) => setKind(e.target.value as SimEditKind)} aria-label={`Change type for ${id}`}>
        {kinds.map((k) => (
          <option key={k} value={k}>
            {kindLabel(k, milestone)}
          </option>
        ))}
      </select>

      {DATE_KINDS.has(edit.kind) && (
        <input
          type="date"
          value={dateValue}
          max={edit.kind === "finish_on" ? undefined : simDate}
          min={edit.kind === "finish_on" ? addDays(simDate, 1) : undefined}
          onChange={(e) => onChange({ ...edit, value: e.target.value })}
          aria-label={`${kindLabel(edit.kind, milestone)} date for ${id}`}
        />
      )}
      {edit.kind === "complete" && !milestone && activity.status === "not_started" && (
        <>
          <span className="sim-edit-label">started</span>
          <input
            type="date"
            value={edit.actual_start ?? ""}
            max={dateValue || simDate}
            onChange={(e) => onChange({ ...edit, actual_start: e.target.value || null })}
            aria-label={`Actual start for ${id}`}
          />
        </>
      )}
      {edit.kind === "percent_complete" && (
        <>
          <input type="number" min={0} max={100} step={1} value={num} onChange={(e) => setNumber(e.target.value)} aria-label={`% complete for ${id}`} />
          <span className="sim-edit-unit">%</span>
        </>
      )}
      {edit.kind === "remaining_duration" && (
        <>
          <input type="number" min={0} step={0.5} value={num} onChange={(e) => setNumber(e.target.value)} aria-label={`Remaining duration for ${id}`} />
          <span className="sim-edit-unit">days · now {Math.round(activity.remaining_days * 10) / 10}d</span>
        </>
      )}
      {edit.kind === "finish_delay" && (
        <>
          <input type="number" step={1} min={milestone ? 1 : undefined} value={num} onChange={(e) => setNumber(e.target.value)} aria-label={`Working days later for ${id}`} />
          <span className="sim-edit-unit">working days</span>
          <span className="sim-edit-quick">
            {[5, 10, 15].map((d) => (
              <button key={d} type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({ ...edit, value: d })}>
                +{d / 5}w
              </button>
            ))}
          </span>
        </>
      )}

      {delayHint && !error && (
        <span className="sim-edit-hint">
          Finishes about <b>{fmtP6Date(delayHint)}</b> instead of {fmtP6Date(activity.finish)}
        </span>
      )}
      {edit.kind === "percent_complete" && !error && (
        <span className="sim-edit-hint">Remaining duration follows the %: original × (1 − %).</span>
      )}
      {error && <span className="sim-row-error">{error}</span>}
    </div>
  );
}

// --- the setup card ----------------------------------------------------------------

export function ScenarioSetup({
  currentDataDate,
  revisionLabel,
  simDate,
  onSimDate,
  edits,
  activitiesById,
  activities,
  errors,
  dirty,
  running,
  canRun,
  onEdits,
  onRun,
  onReset,
}: {
  currentDataDate: string;
  revisionLabel: string | null;
  simDate: string;
  onSimDate: (d: string) => void;
  edits: SimEdit[];
  activitiesById: Map<string, SimContextActivity>;
  activities: SimContextActivity[];
  errors: Map<string, string>;
  dirty: boolean;
  running: boolean;
  canRun: boolean;
  onEdits: (edits: SimEdit[]) => void;
  onRun: () => void;
  onReset: () => void;
}) {
  const rowsRef = useRef<HTMLTableSectionElement>(null);
  const inScenario = useMemo(() => new Set(edits.map((e) => e.external_id)), [edits]);
  const shift = daysBetween(currentDataDate, simDate);
  const dateError = simDate < currentDataDate ? "The simulation data date can't be before the current data date." : null;

  function add(a: SimContextActivity) {
    const kind = a.is_milestone ? "finish_on" : a.status === "in_progress" ? "complete" : "finish_delay";
    onEdits([...edits, { external_id: a.external_id, kind, value: valueForKind(kind, a, simDate), actual_start: null }]);
    // Focus the new row's first value input once it renders.
    setTimeout(() => {
      const rows = rowsRef.current?.querySelectorAll("tr");
      rows?.[rows.length - 1]?.querySelector<HTMLElement>("input, select")?.focus();
    }, 0);
  }

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
        Changed activities <span className="sim-count">{edits.length}</span>
      </div>
      {edits.length === 0 ? (
        <p className="empty-state sim-changes-empty">
          No changes yet. Add an activity below, then mark it complete, push its finish out, or change what&apos;s left of it — or just move the data date.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="sim-changes">
            <thead>
              <tr>
                <th>Activity</th>
                <th>Now</th>
                <th>Change</th>
                <th aria-label="Remove" />
              </tr>
            </thead>
            <tbody ref={rowsRef}>
              {edits.map((e, i) => {
                const a = activitiesById.get(e.external_id);
                const error = errors.get(e.external_id) ?? null;
                return (
                  <tr key={e.external_id} className={error ? "has-error" : undefined}>
                    <td className="sim-cell-act">
                      <div className="subname">{a?.name ?? e.external_id}</div>
                      <div className="actid">
                        {e.external_id}
                        {a?.is_milestone && <span className="chip chip-neutral sim-ms-chip">Milestone</span>}
                      </div>
                    </td>
                    <td className="sim-cell-now">
                      {a ? (
                        <div className="sim-now">
                          <StatusChip status={a.status} />
                          <span className="sim-now-dates">
                            {a.start ? fmtP6Date(a.start) : null}
                            {a.start && a.finish ? <ArrowRightIcon className="icon" /> : null}
                            {a.finish ? fmtP6Date(a.finish) : null}
                          </span>
                          <FloatBadge days={a.total_float_days} />
                        </div>
                      ) : (
                        <span className="sim-row-error">No longer in the programme</span>
                      )}
                    </td>
                    <td className="sim-cell-edit">
                      {a ? (
                        <ChangeEditor
                          activity={a}
                          edit={e}
                          simDate={simDate}
                          error={error}
                          onChange={(next) => onEdits(edits.map((x, j) => (j === i ? next : x)))}
                        />
                      ) : (
                        error && <span className="sim-row-error">{error}</span>
                      )}
                    </td>
                    <td className="sim-cell-remove">
                      <button
                        type="button"
                        className="act-btn sim-remove"
                        aria-label={`Remove ${e.external_id} from the scenario`}
                        title="Remove"
                        onClick={() => onEdits(edits.filter((_, j) => j !== i))}
                      >
                        <XIcon className="icon icon-sm" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="sim-add">
        <ActivityPicker activities={activities} inScenario={inScenario} onPick={add} />
      </div>

      <div className="sim-runbar">
        <span className="sim-runbar-summary">
          {edits.length === 0 && shift === 0 ? (
            "Add a change or move the data date"
          ) : (
            <>
              <b>
                {edits.length} change{edits.length === 1 ? "" : "s"}
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
        <button type="button" className="btn btn-ghost" onClick={onReset} disabled={running || (edits.length === 0 && shift === 0)}>
          Reset
        </button>
        <button type="button" className="btn btn-primary" onClick={onRun} disabled={!canRun || running || Boolean(dateError)}>
          {running ? "Simulating…" : "Run simulation"}
          {!running && <span className="sim-kbd">Ctrl ↵</span>}
        </button>
      </div>
    </div>
  );
}
