"use client";

import { useState } from "react";
import type { Activity, ActivityRelationship, ActivityUpdatePayload } from "@/lib/types";
import { CheckIcon, ClockIcon, LockIcon } from "@/components/icons";

interface ActivityCardProps {
  activity: Activity;
  relationships: ActivityRelationship[];
  pendingFlag: boolean;
  readOnly: boolean;
  onCommit: (patch: ActivityUpdatePayload) => void;
  onFlag: (relationship: ActivityRelationship, fieldLabel: string, currentValueLabel: string) => void;
}

const STATUS_CHIP: Record<Activity["status"], { label: string; className: string }> = {
  not_started: { label: "Not Started", className: "chip-neutral" },
  in_progress: { label: "In Progress", className: "chip-info" },
  complete: { label: "Complete", className: "chip-good" },
};

export function ActivityCard({ activity, relationships, pendingFlag, readOnly, onCommit, onFlag }: ActivityCardProps) {
  const [percent, setPercent] = useState(activity.percent_complete);
  const statusChip = STATUS_CHIP[activity.status];
  const isComplete = activity.status === "complete";

  return (
    <div className="actcard">
      <div className="actcard-head">
        <div className="actcard-head-top">
          <div>
            <div className="actcard-name">{activity.name}</div>
            <div className="actcard-id">{activity.external_id}</div>
          </div>
          <span className={`chip ${statusChip.className}`}>{statusChip.label}</span>
        </div>
        <div className="actcard-meta">
          {isComplete && activity.actual_start && activity.actual_finish
            ? `Actual: ${activity.actual_start} – ${activity.actual_finish}`
            : activity.planned_finish
              ? `Planned finish ${activity.planned_finish}`
              : "No planned finish set"}
        </div>
      </div>

      {pendingFlag && (
        <div className="pending-tag">
          <ClockIcon className="icon" />
          Change pending admin review
        </div>
      )}

      {!isComplete && (
        <div className="field-group">
          <div className="field-group-label editable">
            <CheckIcon className="icon" /> Direct edit
          </div>
          <div className="pct-row">
            <input
              type="range"
              min={0}
              max={100}
              value={percent}
              disabled={readOnly}
              onChange={(e) => setPercent(Number(e.target.value))}
              onMouseUp={() => onCommit({ percent_complete: percent })}
              onTouchEnd={() => onCommit({ percent_complete: percent })}
              onKeyUp={() => onCommit({ percent_complete: percent })}
            />
            <span className="pct-value">{percent}%</span>
          </div>
          <div className="field-row">
            <div className="field field-editable">
              <label htmlFor={`start-${activity.id}`}>Actual start</label>
              <input
                id={`start-${activity.id}`}
                type="date"
                disabled={readOnly}
                defaultValue={activity.actual_start ?? ""}
                onBlur={(e) => onCommit({ actual_start: e.target.value || null })}
              />
            </div>
            <div className="field field-editable">
              <label htmlFor={`remaining-${activity.id}`}>Remaining duration</label>
              <input
                id={`remaining-${activity.id}`}
                type="number"
                min={0}
                disabled={readOnly}
                defaultValue={activity.remaining_duration_days}
                onBlur={(e) => onCommit({ remaining_duration_days: Number(e.target.value) })}
              />
            </div>
          </div>
        </div>
      )}

      {!isComplete &&
        relationships.map((rel) => {
          const isSuccessorSide = rel.successor_id === activity.id;
          const label = isSuccessorSide ? "Predecessor logic & lag" : "Successor logic & lag";
          const otherId = isSuccessorSide ? rel.predecessor_external_id : rel.successor_external_id;
          const arrow = isSuccessorSide ? "←" : "→";
          const valueLabel = `${rel.link_type} ${arrow} ${otherId ?? "?"}${rel.lag_days ? `, ${rel.lag_days}d` : ""}`;
          return (
            <button
              key={rel.id}
              type="button"
              className="lock-field"
              disabled={readOnly}
              onClick={() => onFlag(rel, label, valueLabel)}
            >
              <span>
                <LockIcon className="icon" style={{ display: "inline", verticalAlign: "-3px", marginRight: ".35rem" }} />
                {label}
              </span>
              <span className="lv">{valueLabel}</span>
            </button>
          );
        })}
    </div>
  );
}
