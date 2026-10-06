"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useProjectContext } from "@/lib/project-context";
import { CheckIcon } from "@/components/icons";
import { EmptyState } from "@/components/EmptyState";
import { NoBaselineIllo } from "@/components/illustrations";

// Top-nav section keys that stay locked until the selected project has a
// baseline programme. Planning / Portfolio / Administration are deliberately
// left open so the planner can import the schedule and lock the baseline in
// the first place.
export const BASELINE_GATED_SECTIONS = new Set(["overview", "execution", "risk", "reporting"]);

// Pages inside a gated section that measure the programme against itself rather
// than against a baseline, so the gate would only be in the way. Float Path
// reads total float, early/late dates and the relationship set — all of which
// P6 computed and the .xer import stored, none of which involve a baseline.
// My Desk is the user's own pins, notes and approval queues — a project with no
// baseline yet mustn't lock anyone out of their own notes.
// Portfolio Dashboard spans every project, so one project lacking a baseline
// mustn't hide it.
export const BASELINE_UNGATED_PATHS = new Set(["/reporting/float-path", "/execution/my-desk", "/portfolio/dashboard"]);

export function isBaselineGated(sectionKey: string | undefined, pathname: string | null): boolean {
  if (pathname && BASELINE_UNGATED_PATHS.has(pathname)) return false;
  return BASELINE_GATED_SECTIONS.has(sectionKey ?? "");
}

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
        <span className="crumb">Setup</span>
      </div>
      <div className="a-content">
        <div className="card" style={{ maxWidth: 560 }}>
          <EmptyState
            art={<NoBaselineIllo />}
            title="This project has no baseline yet"
            body="Delivery, Reports, EVM and Risk measure the project against a locked baseline programme."
          />
          <ol className="setup-steps">
            <li className="is-done">
              <span className="setup-num">
                <CheckIcon className="icon icon-xs" />
              </span>
              Create the project
              <span className="setup-note">Done</span>
            </li>
            <li>
              <span className="setup-num">2</span>
              Upload the schedule (.xer)
              <Link className="btn btn-secondary btn-sm" href="/project-files">
                Programs
              </Link>
            </li>
            <li>
              <span className="setup-num">3</span>
              Lock the baseline
              <Link className="btn btn-primary btn-sm" href="/planning/baselines">
                Go to Baselines
              </Link>
            </li>
            <li className="is-muted">
              <span className="setup-num">4</span>
              Open an update period for subcontractors
              <span className="setup-note">Not yet available</span>
            </li>
          </ol>
        </div>
      </div>
    </>
  );
}
