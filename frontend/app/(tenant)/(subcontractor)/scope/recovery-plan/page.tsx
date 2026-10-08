"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { ClockIcon } from "@/components/icons";
import { fmtP6Date } from "@/components/reporting/format";
import { RecoveryPlanPanel } from "@/components/recovery/RecoveryPlanPanel";
import type { Project, RecoveryPlan, SlipReport, SlipRow, UpdatePeriod } from "@/lib/types";

export default function SubRecoveryPlanPage() {
  const { showToast } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [period, setPeriod] = useState<UpdatePeriod | null>(null);
  const [report, setReport] = useState<SlipReport | null>(null);
  const [plans, setPlans] = useState<Record<string, RecoveryPlan>>({});
  const [loading, setLoading] = useState(true);
  // ?activity=… (a mention): scroll to that card once loaded.
  const focusActivity = useRef<string>("");

  const load = useCallback(async () => {
    try {
      const projects = await api.get<Project[]>("/projects");
      const active = projects[0] ?? null;
      setProject(active);
      if (!active) return;
      const periods = await api.get<UpdatePeriod[]>(`/update-periods?project_id=${active.id}`);
      setPeriod(periods.find((p) => p.status === "open") ?? null);
      const r = await api.get<SlipReport>(`/projects/${active.id}/recovery-plan`);
      setReport(r);
      const detail = await Promise.all(
        r.slipped.filter((s) => s.plan).map((s) => api.get<RecoveryPlan>(`/projects/${active.id}/recovery-plan/plans/${s.plan!.id}`)),
      );
      setPlans(Object.fromEntries(detail.map((p) => [p.id, p])));
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    focusActivity.current = new URLSearchParams(window.location.search).get("activity") ?? "";
    load();
  }, [load]);

  useEffect(() => {
    const code = focusActivity.current;
    if (loading || !code) return;
    focusActivity.current = "";
    window.setTimeout(() => document.getElementById(`rp-card-${code}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
  }, [loading]);

  async function loadPlan(id: string) {
    if (!project) return;
    const p = await api.get<RecoveryPlan>(`/projects/${project.id}/recovery-plan/plans/${id}`);
    setPlans((prev) => ({ ...prev, [id]: p }));
  }

  async function startPlan(row: SlipRow) {
    if (!project) return;
    try {
      const p = await api.post<RecoveryPlan>(`/projects/${project.id}/recovery-plan/plans`, {
        activity_external_id: row.external_id,
      });
      setPlans((prev) => ({ ...prev, [p.id]: p }));
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not start the plan.", "error");
    }
  }

  const slipped = report?.slipped ?? [];

  return (
    <div className="sub-page">
      <div className="sub-frame">
        <div className="sub-header">
          <div className="sub-header-top">
            <div className="sub-id">
              <div>
                <div className="sub-company">Recovery Plans</div>
                <div className="sub-project">{project?.name ?? "—"}</div>
              </div>
            </div>
          </div>
          <div className={`deadline-banner${period ? "" : " good"}`}>
            <ClockIcon className="icon" />
            {period ? `${period.label} — submit your recovery plans` : "No open update period right now"}
          </div>
        </div>

        <div className="sub-body">
          <Link href="/scope" style={{ fontSize: ".8125rem", color: "var(--accent-strong)" }}>
            ‹ Back to My Activities
          </Link>

          {loading ? (
            <p className="page-desc">Loading…</p>
          ) : slipped.length === 0 ? (
            <p className="empty-state">None of your activities slipped since the last update.</p>
          ) : (
            slipped.map((row) => {
              const plan = row.plan ? plans[row.plan.id] : null;
              return (
                <div key={row.external_id} id={`rp-card-${row.external_id}`} className="card rp-sub-card">
                  <div className="rp-sub-head">
                    <div>
                      <div className="subname">{row.name}</div>
                      <div className="actid">{row.external_id}</div>
                    </div>
                    <span className="rp-chips">
                      {(row.is_critical || row.is_longest_path) && <span className="chip chip-crit">Critical</span>}
                      <span className="chip chip-neutral num">+{row.slip_days}d</span>
                    </span>
                  </div>
                  <div className="rp-sub-dates num">
                    Finish {fmtP6Date(row.prev_finish)} → {fmtP6Date(row.curr_finish)}
                  </div>

                  {!plan && (
                    <div className="rp-noplan">
                      <p>{period ? "Say why it slipped and how you'll win the time back." : "Plans can be started while an update period is open."}</p>
                      <button className="btn btn-primary btn-sm" disabled={!period} onClick={() => startPlan(row)}>
                        Start recovery plan
                      </button>
                    </div>
                  )}

                  {plan && project && (
                    <RecoveryPlanPanel
                      projectId={project.id}
                      plan={plan}
                      canTrack
                      canAcknowledge={false}
                      meId={null}
                      onChanged={async (statusMoved) => {
                        if (statusMoved) await load();
                        else await loadPlan(plan.id);
                      }}
                    />
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
