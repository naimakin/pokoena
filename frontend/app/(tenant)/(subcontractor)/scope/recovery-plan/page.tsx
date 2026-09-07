"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { ClockIcon } from "@/components/icons";
import { ActionItems } from "@/components/ActionItems";
import type { Project, RecoveryPlan, SlipReport, SlipRow, UpdatePeriod } from "@/lib/types";

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

export default function SubRecoveryPlanPage() {
  const { showToast } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [period, setPeriod] = useState<UpdatePeriod | null>(null);
  const [report, setReport] = useState<SlipReport | null>(null);
  const [plans, setPlans] = useState<Record<string, RecoveryPlan>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
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
    load();
  }, [load]);

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
      showToast(err instanceof ApiError ? err.message : "Could not start the plan.");
    }
  }

  async function submitPlan(id: string) {
    if (!project) return;
    try {
      await api.post(`/projects/${project.id}/recovery-plan/plans/${id}/submit`);
      await Promise.all([load(), loadPlan(id)]);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not submit.");
    }
  }

  const slipped = report?.slipped ?? [];
  const editable = Boolean(period);

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
                <div key={row.external_id} className="card" style={{ padding: "0.9rem 1rem", marginTop: ".8rem" }}>
                  <div style={{ fontWeight: 600 }}>{row.name}</div>
                  <div className="actid">
                    {row.external_id}
                    {row.is_critical ? " · CRITICAL" : ""}
                  </div>
                  <div className="mono" style={{ fontSize: ".75rem", color: "var(--text-muted)", margin: ".3rem 0" }}>
                    {fmt(row.prev_finish)} → {fmt(row.curr_finish)} · +{row.slip_days}d
                  </div>

                  {!plan && (
                    <button className="btn btn-primary btn-sm" disabled={!editable} onClick={() => startPlan(row)}>
                      Start recovery plan
                    </button>
                  )}

                  {plan && (
                    <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
                      <textarea
                        defaultValue={plan.summary ?? ""}
                        placeholder="Why did it slip? (required to submit)"
                        disabled={!editable || !["draft", "needs_revision"].includes(plan.status)}
                        className="field-editable"
                        onBlur={(e) =>
                          e.target.value !== (plan.summary ?? "") &&
                          api
                            .patch(`/projects/${project!.id}/recovery-plan/plans/${plan.id}`, { summary: e.target.value })
                            .then(() => loadPlan(plan.id))
                        }
                        style={{ width: "100%", minHeight: 44 }}
                      />
                      <ActionItems
                        basePath={`/projects/${project!.id}/recovery-plan/plans/${plan.id}`}
                        items={plan.items ?? []}
                        editable={editable && ["draft", "needs_revision"].includes(plan.status)}
                        trackable={plan.status === "accepted"}
                        onChanged={() => loadPlan(plan.id)}
                      />
                      {plan.review_note && plan.status === "needs_revision" && (
                        <div className="banner warn"><span className="banner-text">Reviewer: {plan.review_note}</span></div>
                      )}
                      <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>Status: {plan.status}</div>
                      {editable && ["draft", "needs_revision"].includes(plan.status) && (
                        <button className="btn btn-primary btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => submitPlan(plan.id)}>
                          Submit plan
                        </button>
                      )}
                    </div>
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
