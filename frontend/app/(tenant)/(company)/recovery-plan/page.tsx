"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { RecoveryPlan, SlipReport, SlipRow, User } from "@/lib/types";
import { ActionItems } from "@/components/ActionItems";
import { AlertTriangleIcon, DownloadIcon } from "@/components/icons";

type Grouping = "contractor" | "wbs" | "flat";
const GROUP_KEY = "poko:recovery:grouping";

const PLAN_CHIP: Record<string, string> = {
  none: "chip-neutral",
  draft: "chip-info",
  submitted: "chip-warn",
  accepted: "chip-good",
  needs_revision: "chip-crit",
};
const PLAN_LABEL: Record<string, string> = {
  none: "No plan",
  draft: "Draft",
  submitted: "Submitted",
  accepted: "Accepted",
  needs_revision: "Needs revision",
};

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export default function RecoveryPlanPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();

  const [report, setReport] = useState<SlipReport | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [grouping, setGrouping] = useState<Grouping>("contractor");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [minSlip, setMinSlip] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [plans, setPlans] = useState<Record<string, RecoveryPlan>>({});
  const [reviewNote, setReviewNote] = useState<Record<string, string>>({});

  useEffect(() => {
    try {
      const g = localStorage.getItem(GROUP_KEY);
      if (g === "contractor" || g === "wbs" || g === "flat") setGrouping(g);
    } catch {
      /* ignore */
    }
    api.get<User>("/auth/me").then(setMe).catch(() => setMe(null));
  }, []);

  const load = useCallback(async () => {
    if (!project) {
      setReport(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setReport(await api.get<SlipReport>(`/projects/${project.id}/recovery-plan`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the recovery plan.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  const isAdmin = me?.role === "company_admin";

  async function loadPlan(id: string) {
    if (!project) return;
    try {
      const p = await api.get<RecoveryPlan>(`/projects/${project.id}/recovery-plan/plans/${id}`);
      setPlans((prev) => ({ ...prev, [id]: p }));
    } catch {
      /* ignore */
    }
  }

  function toggle(row: SlipRow) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(row.external_id)) next.delete(row.external_id);
      else {
        next.add(row.external_id);
        if (row.plan) loadPlan(row.plan.id);
      }
      return next;
    });
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

  async function planAction(planId: string, path: string, body?: unknown) {
    if (!project) return;
    try {
      await api.post(`/projects/${project.id}/recovery-plan/plans/${planId}${path}`, body);
      await Promise.all([load(), loadPlan(planId)]);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Action failed.");
    }
  }

  const rows = useMemo(() => {
    let r = report?.slipped ?? [];
    if (criticalOnly) r = r.filter((x) => x.is_critical || x.is_longest_path);
    if (minSlip > 0) r = r.filter((x) => x.slip_days >= minSlip);
    return r;
  }, [report, criticalOnly, minSlip]);

  const groups = useMemo(() => {
    if (grouping === "flat") return [{ key: "all", label: `${rows.length} activities`, rows }];
    const map = new Map<string, SlipRow[]>();
    for (const row of rows) {
      const key =
        grouping === "contractor"
          ? row.scope_name ?? "Self-perform / unassigned"
          : row.wbs_path ?? "No WBS";
      map.set(key, [...(map.get(key) ?? []), row]);
    }
    return [...map.entries()].map(([label, rs]) => ({ key: label, label, rows: rs }));
  }, [grouping, rows]);

  if (loading) {
    return (
      <div className="a-content">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="a-content">
        <p className="login-error" style={{ maxWidth: 420 }}>{error}</p>
      </div>
    );
  }
  if (!project || !report) {
    return (
      <div className="a-content">
        <p className="page-desc">No project selected.</p>
      </div>
    );
  }

  const { summary } = report;

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project.name} / <b>Recovery Plan</b>
        </span>
      </div>
      <div className="a-content recovery-print">
        <div className="page-head">
          <div>
            <div className="page-title">Recovery Plan</div>
            <div className="page-desc">
              {report.comparison_basis === "none"
                ? "Slippage tracking starts once two schedule updates carry an activity snapshot."
                : `Slippage between ${report.from_import?.revision_label ?? "—"} (${fmt(
                    report.from_import?.data_date ?? report.from_import?.imported_at,
                  )}) and ${report.to_import?.revision_label ?? "—"} (${fmt(
                    report.to_import?.data_date ?? report.to_import?.imported_at,
                  )})`}
            </div>
          </div>
          <button className="btn btn-secondary no-print" onClick={() => window.print()}>
            <DownloadIcon className="icon" /> Print
          </button>
        </div>

        {report.comparison_basis === "none" ? (
          <div className="card">
            <p className="empty-state">
              Upload at least two schedule updates (UPD-1, UPD-2…) from Program Library. The
              recovery plan compares the two most recent.
            </p>
          </div>
        ) : rows.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              No activities slipped between {report.from_import?.revision_label} and{" "}
              {report.to_import?.revision_label}.
            </p>
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: "0.9rem 1.1rem", display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
              <b className="num" style={{ fontSize: "1rem" }}>
                {summary.plans_submitted} of {summary.plans_required} plans submitted
              </b>
              <span className="chip chip-good">{summary.plans_accepted} accepted</span>
              {summary.critical_slipped_count > 0 && (
                <span className="chip chip-crit">
                  <AlertTriangleIcon className="icon" style={{ width: 12, height: 12 }} />
                  {summary.critical_slipped_count} critical
                </span>
              )}
              <span className="spacer" style={{ flex: 1 }} />
              <div className="segmented no-print">
                {(["contractor", "wbs", "flat"] as Grouping[]).map((g) => (
                  <button
                    key={g}
                    className={grouping === g ? "active" : ""}
                    onClick={() => {
                      setGrouping(g);
                      try {
                        localStorage.setItem(GROUP_KEY, g);
                      } catch {
                        /* ignore */
                      }
                    }}
                  >
                    {g === "contractor" ? "By contractor" : g === "wbs" ? "By WBS" : "Flat"}
                  </button>
                ))}
              </div>
              <label className="no-print" style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                <input type="checkbox" checked={criticalOnly} onChange={(e) => setCriticalOnly(e.target.checked)} />
                Critical only
              </label>
              <label className="no-print" style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                Slip ≥
                <input
                  type="number"
                  min={0}
                  value={minSlip}
                  onChange={(e) => setMinSlip(Math.max(0, Number(e.target.value) || 0))}
                  style={{ width: 56 }}
                />
                d
              </label>
            </div>

            {groups.map((group) => (
              <div key={group.key} className="card">
                <div className="card-head">
                  <div className="card-title">{group.label}</div>
                  <div className="card-title-sub">{group.rows.length} slipped</div>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Activity</th>
                        <th>Finish (prev → curr)</th>
                        <th style={{ textAlign: "right" }}>Slip</th>
                        <th>Plan</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {group.rows.map((row) => {
                        const open = expanded.has(row.external_id);
                        const plan = row.plan ? plans[row.plan.id] : null;
                        const planStatus = row.plan?.status ?? "none";
                        const canAuthor = !row.scope_id; // company self-perform
                        return (
                          <Fragment key={row.external_id}>
                            <tr
                              className={row.is_critical ? "critical" : undefined}
                              onClick={() => toggle(row)}
                              style={{ cursor: "pointer" }}
                            >
                              <td>
                                <div className="subname">{row.name}</div>
                                <div className="actid">
                                  {row.external_id}
                                  {row.is_critical ? " · CRITICAL" : ""}
                                </div>
                              </td>
                              <td className="mono">
                                {fmt(row.prev_finish)} → {fmt(row.curr_finish)}
                              </td>
                              <td className="num" style={{ textAlign: "right", color: "var(--crit)" }}>
                                +{row.slip_days}d
                              </td>
                              <td>
                                <span className={`chip ${PLAN_CHIP[planStatus]}`}>{PLAN_LABEL[planStatus]}</span>
                                {row.needs_attention && (
                                  <span className="chip chip-crit" style={{ marginLeft: 4 }}>action</span>
                                )}
                              </td>
                              <td className="num" style={{ textAlign: "right" }}>{open ? "▾" : "▸"}</td>
                            </tr>
                            {open && (
                              <tr>
                                <td colSpan={5} style={{ background: "var(--surface-2)" }}>
                                  <div style={{ padding: ".6rem .2rem", display: "flex", flexDirection: "column", gap: ".6rem" }}>
                                    <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                                      {row.status} · {row.percent_complete}% · WBS {row.wbs_path ?? "—"}
                                    </div>

                                    {!row.plan && canAuthor && (
                                      <button className="btn btn-primary btn-sm no-print" style={{ alignSelf: "flex-start" }} onClick={() => startPlan(row)}>
                                        Start plan
                                      </button>
                                    )}
                                    {!row.plan && !canAuthor && (
                                      <p className="empty-state" style={{ padding: ".3rem 0" }}>
                                        Awaiting a recovery plan from {row.scope_name}.
                                      </p>
                                    )}

                                    {plan && (
                                      <>
                                        {plan.summary && (
                                          <div style={{ fontSize: ".8125rem" }}>
                                            <b>Root cause: </b>
                                            {plan.summary}
                                          </div>
                                        )}
                                        {canAuthor && ["draft", "needs_revision"].includes(plan.status) && (
                                          <textarea
                                            defaultValue={plan.summary ?? ""}
                                            placeholder="Root cause / narrative…"
                                            className="field-editable no-print"
                                            onBlur={(e) =>
                                              e.target.value !== (plan.summary ?? "") &&
                                              api
                                                .patch(`/projects/${project.id}/recovery-plan/plans/${plan.id}`, { summary: e.target.value })
                                                .then(() => loadPlan(plan.id))
                                            }
                                            style={{ width: "100%", minHeight: 48 }}
                                          />
                                        )}
                                        <ActionItems
                                          basePath={`/projects/${project.id}/recovery-plan/plans/${plan.id}`}
                                          items={plan.items ?? []}
                                          editable={canAuthor && ["draft", "needs_revision"].includes(plan.status)}
                                          trackable={plan.status === "accepted"}
                                          onChanged={() => loadPlan(plan.id)}
                                        />
                                        {plan.review_note && plan.status === "needs_revision" && (
                                          <div className="banner warn"><span className="banner-text">Reviewer: {plan.review_note}</span></div>
                                        )}
                                        <div className="no-print" style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
                                          {canAuthor && ["draft", "needs_revision"].includes(plan.status) && (
                                            <button className="btn btn-primary btn-sm" onClick={() => planAction(plan.id, "/submit")}>
                                              Submit plan
                                            </button>
                                          )}
                                          {isAdmin && plan.status === "submitted" && (
                                            <>
                                              <input
                                                placeholder="Review note"
                                                value={reviewNote[plan.id] ?? ""}
                                                onChange={(e) => setReviewNote((p) => ({ ...p, [plan.id]: e.target.value }))}
                                                style={{ width: 200 }}
                                              />
                                              <button
                                                className="btn btn-secondary btn-sm"
                                                onClick={() => planAction(plan.id, "/review", { decision: "needs_revision", note: reviewNote[plan.id] })}
                                              >
                                                Return for revision
                                              </button>
                                              <button
                                                className="btn btn-primary btn-sm"
                                                onClick={() => planAction(plan.id, "/review", { decision: "accept", note: reviewNote[plan.id] })}
                                              >
                                                Accept plan
                                              </button>
                                            </>
                                          )}
                                        </div>
                                      </>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </>
  );
}
