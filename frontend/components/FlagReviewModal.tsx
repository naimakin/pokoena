"use client";

import { useEffect, useState } from "react";
import { AlertTriangleIcon } from "@/components/icons";

interface FlagReviewModalProps {
  open: boolean;
  activityLabel: string;
  fieldLabel: string;
  currentValueLabel: string;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (newValue: string, justification: string) => void;
}

export function FlagReviewModal({
  open,
  activityLabel,
  fieldLabel,
  currentValueLabel,
  submitting,
  onCancel,
  onSubmit,
}: FlagReviewModalProps) {
  const [newValue, setNewValue] = useState("");
  const [justification, setJustification] = useState("");

  useEffect(() => {
    if (open) {
      setNewValue("");
      setJustification("");
    }
  }, [open]);

  if (!open) return null;

  const canSubmit = newValue.trim().length > 0 && justification.trim().length > 0 && !submitting;

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="modal">
        <div className="modal-head">
          <AlertTriangleIcon className="icon-lg" />
          <div>
            <div className="modal-title">Flag for admin review</div>
            <div className="modal-desc">
              Logic, lag, and dependency changes require project controls approval before they take effect.
            </div>
          </div>
        </div>
        <div className="modal-body">
          <div className="modal-diff">
            <div className="lbl">Changing</div>
            <div style={{ fontSize: ".8125rem", fontWeight: 500 }}>{fieldLabel}</div>
            <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
              {activityLabel} &middot; currently {currentValueLabel}
            </div>
          </div>
          <div className="field">
            <label htmlFor="flag-new-value">
              Requested value <span style={{ color: "var(--crit)" }}>*</span>
            </label>
            <input
              id="flag-new-value"
              type="text"
              placeholder="e.g. FS, 5d lag"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="flag-note">
              Justification <span style={{ color: "var(--crit)" }}>*</span>
            </label>
            <textarea
              id="flag-note"
              placeholder="Explain why this change is needed…"
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
            />
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={!canSubmit}
            onClick={() => onSubmit(newValue.trim(), justification.trim())}
          >
            {submitting ? "Submitting…" : "Submit for review"}
          </button>
        </div>
      </div>
    </div>
  );
}
