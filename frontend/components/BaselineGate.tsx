"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useProjectContext } from "@/lib/project-context";
import { LockIcon } from "@/components/icons";

// Top-nav section keys that stay locked until the selected project has a
// baseline programme. Planning / Portfolio / Documents / Administration are
// deliberately left open so the planner can import the schedule and lock the
// baseline in the first place.
export const BASELINE_GATED_SECTIONS = new Set(["dashboard", "execution", "risk", "reporting", "ai"]);

export function BaselineGate({ gated, children }: { gated: boolean; children: ReactNode }) {
  const { project, baselineReady } = useProjectContext();

  // Only block once we positively know there's no baseline (baselineReady ===
  // false). `null` (still loading) and `true` both render the page.
  if (!gated || !project || baselineReady !== false) {
    return <>{children}</>;
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project.name} / <b>Set up baseline</b>
        </span>
      </div>
      <div className="a-content">
        <div className="card" style={{ padding: "1.5rem 1.35rem", maxWidth: 560 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: ".55rem" }}>
              <LockIcon className="icon" />
              <span style={{ fontFamily: "var(--font-display)", fontSize: "1.125rem", fontWeight: 700 }}>
                This project has no baseline yet
              </span>
            </div>
            <p style={{ fontSize: ".8125rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Execution, Reporting, EVM, Risk and AI all measure the project against a locked baseline
              programme. Upload the baseline <span className="mono">.xer</span> on{" "}
              <b>Planning → Baselines</b> first — its resources and dates are frozen there, and every later
              update programme is compared back to it.
            </p>
            <div>
              <Link className="btn btn-primary" href="/planning/baselines">
                <LockIcon className="icon" /> Go to Baselines
              </Link>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
