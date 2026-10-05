"use client";

// Reusable "expand to a larger popup" wrapper for chart cards — reuses the
// existing .modal-overlay/.act-btn idiom (see FlagReviewModal.tsx) with a
// wider .modal-lg panel instead of the confirmation-dialog-sized .modal.
// Charts in this project (ScurveChart, TrendLine) scale via SVG
// viewBox, so the same children render larger inside the wider panel with no
// separate "large" chart variant needed — no data is refetched.

import { useEffect, useId, useState, type ReactNode } from "react";
import { ExpandIcon, XIcon } from "@/components/icons";

interface ExpandableChartCardProps {
  title: ReactNode;
  subtitle?: string;
  headerExtra?: ReactNode;
  children: ReactNode;
  pad?: boolean;
}

export function ExpandableChartCard({ title, subtitle, headerExtra, children, pad = true }: ExpandableChartCardProps) {
  const [open, setOpen] = useState(false);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">{title}</div>
          {subtitle && <div className="card-title-sub">{subtitle}</div>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
          {headerExtra}
          <button
            type="button"
            className="act-btn chart-expand-btn"
            aria-label="Expand chart"
            onClick={() => setOpen(true)}
          >
            <ExpandIcon className="icon" />
          </button>
        </div>
      </div>
      <div style={pad ? { padding: "1rem 1.1rem" } : undefined}>{children}</div>

      {open && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div className="modal-lg" role="dialog" aria-modal="true" aria-labelledby={titleId}>
            <div className="modal-head">
              <div>
                <div className="modal-title" id={titleId}>{title}</div>
                {subtitle && <div className="modal-desc">{subtitle}</div>}
              </div>
              <button type="button" className="act-btn" aria-label="Close" onClick={() => setOpen(false)}>
                <XIcon className="icon" />
              </button>
            </div>
            <div className="modal-body">{children}</div>
          </div>
        </div>
      )}
    </div>
  );
}
