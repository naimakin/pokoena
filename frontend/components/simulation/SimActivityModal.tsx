"use client";

// Edits one activity in the scenario — the same fields the Activity modal
// edits in Project Activities (status, actual dates, % complete, remaining
// duration), plus the two ways to say "it finishes later": P6's Expected
// Finish, or N working days later. Nothing is saved to the live schedule.

import { useState } from "react";
import { XIcon } from "@/components/icons";
import { FloatBadge, fmtP6Date } from "@/components/reporting/format";
import { toDays } from "@/lib/duration";
import { displayFinish, displayStart, FINISH_MILESTONE, isMilestone, START_MILESTONE } from "@/lib/schedule-dates";
import {
  addDays,
  liveDraft,
  originalDays,
  sameDraft,
  SUMMARY_TYPES,
  validateDraft,
  withPercent,
  withStatus,
  type Draft,
} from "@/lib/simulation";
import type { Activity, ActivityStatus } from "@/lib/types";
import { StatusChip } from "./ScenarioSetup";

const STATUS_OPTIONS: { value: ActivityStatus; label: string }[] = [
  { value: "not_started", label: "Not Started" },
  { value: "in_progress", label: "In Progress" },
  { value: "complete", label: "Completed" },
];

export function SimActivityModal({
  activity,
  draft: initial,
  simDate,
  inScenario,
  onApply,
  onRemove,
  onClose,
}: {
  activity: Activity;
  draft: Draft;
  simDate: string;
  inScenario: boolean;
  onApply: (d: Draft) => void;
  onRemove: () => void;
  onClose: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const milestone = isMilestone(activity);
  const live = liveDraft(activity);
  const summary = SUMMARY_TYPES.has(activity.task_type ?? "");
  const error = validateDraft(activity, d, simDate);
  const unchanged = sameDraft(d, live);
  const statusOptions = milestone ? STATUS_OPTIONS.filter((s) => s.value !== "in_progress") : STATUS_OPTIONS;
  const original = originalDays(activity);
  const finishNow = displayFinish(activity);
  const done = d.status === "complete";

  function setDelay(days: number | null) {
    setD((x) => ({ ...x, finish_delay_days: days, expected_finish: null }));
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal sim-modal" role="dialog" aria-modal="true" aria-labelledby="sim-act-title">
        <div className="modal-head sim-modal-head">
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="act-modal-crumb">
              <span className="mono">{activity.external_id}</span>
              {milestone && <span> · Milestone</span>}
            </div>
            <div className="modal-title" id="sim-act-title">
              {activity.name}
            </div>
            <div className="sim-modal-now">
              <span>Now:</span>
              <StatusChip status={activity.status} />
              <span className="mono">
                {fmtP6Date(displayStart(activity))} → {fmtP6Date(finishNow)}
              </span>
              <FloatBadge days={toDays(activity.total_float_hours, activity)} />
            </div>
          </div>
          <button type="button" className="act-btn" onClick={onClose} aria-label="Close">
            <XIcon className="icon" />
          </button>
        </div>

        <div className="modal-body">
          {summary ? (
            <p className="act-modal-note">
              Summary and level-of-effort activities take their dates from the activities they span; change those instead.
            </p>
          ) : (
            <>
              <p className="sim-modal-note">Changes apply to this scenario only — the live schedule isn&apos;t touched.</p>
              <div className="act-field-grid">
                <label className="field">
                  <span>Status</span>
                  <select value={d.status} onChange={(e) => setD((x) => withStatus(activity, x, e.target.value as ActivityStatus, simDate))}>
                    {statusOptions.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>% Complete</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    disabled={milestone || d.status !== "in_progress"}
                    value={d.percent_complete}
                    onChange={(e) => setD((x) => withPercent(activity, x, Number(e.target.value) || 0))}
                  />
                </label>
                {activity.task_type !== FINISH_MILESTONE && (
                  <label className="field">
                    <span>{milestone ? "Actual date" : "Actual Start"}</span>
                    <input
                      type="date"
                      max={simDate}
                      disabled={d.status === "not_started"}
                      value={d.actual_start ?? ""}
                      onChange={(e) =>
                        setD((x) => ({
                          ...x,
                          actual_start: e.target.value || null,
                          ...(milestone ? { actual_finish: e.target.value || null } : {}),
                        }))
                      }
                    />
                  </label>
                )}
                {activity.task_type !== START_MILESTONE && (
                  <label className="field">
                    <span>{milestone ? "Actual date" : "Actual Finish"}</span>
                    <input
                      type="date"
                      max={simDate}
                      disabled={!done}
                      value={d.actual_finish ?? ""}
                      onChange={(e) =>
                        setD((x) => ({
                          ...x,
                          actual_finish: e.target.value || null,
                          ...(milestone ? { actual_start: e.target.value || null } : {}),
                        }))
                      }
                    />
                  </label>
                )}
                {!milestone && (
                  <label className="field">
                    <span>
                      Remaining Duration (days)
                      {original != null && <span className="sim-field-hint"> · original {Math.round(original * 10) / 10}d</span>}
                    </span>
                    <input
                      type="number"
                      min={0}
                      step={0.5}
                      disabled={done}
                      value={d.remaining_days}
                      onChange={(e) => setD((x) => ({ ...x, remaining_days: Math.max(0, Number(e.target.value) || 0) }))}
                    />
                  </label>
                )}
              </div>

              <div className="sim-modal-later">
                <div className="sim-modal-later-title">Finishes later</div>
                <div className="act-field-grid">
                  <label className="field">
                    <span>By working days</span>
                    <div className="sim-modal-inline">
                      <input
                        type="number"
                        min={milestone ? 0 : undefined}
                        step={1}
                        disabled={done}
                        value={d.finish_delay_days ?? ""}
                        placeholder="0"
                        onChange={(e) => setDelay(e.target.value === "" ? null : Number(e.target.value))}
                      />
                      {[5, 10, 15].map((n) => (
                        <button key={n} type="button" className="btn btn-ghost btn-sm" disabled={done} onClick={() => setDelay(n)} title={`${n} working days`}>
                          +{n / 5}w
                        </button>
                      ))}
                    </div>
                  </label>
                  <label className="field">
                    <span>{milestone ? "Or move to (no earlier than)" : "Or expected finish (P6)"}</span>
                    <input
                      type="date"
                      min={addDays(simDate, 1)}
                      disabled={done}
                      value={d.expected_finish ?? ""}
                      onChange={(e) => setD((x) => ({ ...x, expected_finish: e.target.value || null, finish_delay_days: null }))}
                    />
                  </label>
                </div>
                {!done && finishNow && (d.finish_delay_days || d.expected_finish) ? (
                  <p className="sim-field-hint">
                    Finishes {d.expected_finish ? `on ${fmtP6Date(d.expected_finish)}` : `${d.finish_delay_days} working days later than it would`}
                    {" "}instead of about {fmtP6Date(finishNow)} — the run works out the exact date on the activity&apos;s calendar.
                  </p>
                ) : null}
              </div>
              {error && <p className="sim-row-error">{error}</p>}
            </>
          )}
        </div>

        <div className="modal-foot">
          {inScenario && (
            <button type="button" className="btn btn-ghost sim-modal-remove" onClick={onRemove}>
              Remove from scenario
            </button>
          )}
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={summary || Boolean(error) || (unchanged && !inScenario)}
            onClick={() => (unchanged ? onRemove() : onApply(d))}
          >
            {unchanged && inScenario ? "Reset to live" : inScenario ? "Update scenario" : "Add to scenario"}
          </button>
        </div>
      </div>
    </div>
  );
}
