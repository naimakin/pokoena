"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import { ActionItems } from "@/components/ActionItems";
import { DownloadIcon } from "@/components/icons";
import type { MitigationStrategyValue, RiskItem, User } from "@/lib/types";

type Grouping = "status" | "category" | "flat";
const GROUP_KEY = "poko:risk-mitigation:grouping";
const STRATEGIES: MitigationStrategyValue[] = ["mitigate", "avoid", "transfer", "accept"];

const MIT_CHIP: Record<string, string> = {
  none: "chip-neutral",
  draft: "chip-info",
  submitted: "chip-warn",
  accepted: "chip-good",
  needs_revision: "chip-crit",
};
const MIT_LABEL: Record<string, string> = {
  none: "No plan",
  draft: "Draft",
  submitted: "Submitted",
  accepted: "Accepted",
  needs_revision: "Needs revision",
};

const PLAN_REQUIRED_SCORE = 10;

function planRequired(r: RiskItem): boolean {
  return r.score >= PLAN_REQUIRED_SCORE && r.status !== "closed" && r.status !== "occurred";
}
function editableStatus(s: string): boolean {
  return s === "none" || s === "draft" || s === "needs_revision";
}

export default function RiskMitigationPlansPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [grouping, setGrouping] = useState<Grouping>("status");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [reviewNote, setReviewNote] = useState<Record<string, string>>({});

  useEffect(() => {
    try {
      const g = localStorage.getItem(GROUP_KEY);
      if (g === "status" || g === "category" || g === "flat") setGrouping(g);
    } catch {
      /* ignore */
    }
    api.get<User>("/auth/me").then(setMe).catch(() => setMe(null));
  }, []);

  const load = useCallback(async () => {
    if (!project) {
      setRisks([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setRisks(await api.get<RiskItem[]>(`/projects/${project.id}/risks?embed_items=1`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load mitigation plans.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  const isAdmin = me?.role === "company_admin";

  const rows = useMemo(
    () => risks.filter((r) => planRequired(r) || r.mitigation_status !== "none"),
    [risks],
  );
  const groups = useMemo(() => {
    if (grouping === "flat") return [{ key: "all", label: `${rows.length} risks`, rows }];
    const m = new Map<string, RiskItem[]>();
    for (const r of rows) {
      const k = grouping === "status" ? r.status : r.category ?? "Uncategorised";
      m.set(k, [...(m.get(k) ?? []), r]);
    }
    return [...m.entries()].map(([label, rs]) => ({ key: label, label, rows: rs }));
  }, [grouping, rows]);

  const requiredCount = rows.filter(planRequired).length;
  const submittedCount = rows.filter((r) => planRequired(r) && ["submitted", "accepted"].includes(r.mitigation_status)).length;
  const acceptedCount = rows.filter((r) => r.mitigation_status === "accepted").length;

  async function patchRisk(id: string, body: Record<string, unknown>) {
    if (!project) return;
    try {
      await api.patch(`/projects/${project.id}/risks/${id}`, body);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Update failed.");
    }
  }
  async function mitigationAction(id: string, path: string, body?: unknown) {
    if (!project) return;
    try {
      await api.post(`/projects/${project.id}/risks/${id}/mitigation/${path}`, body);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Action failed.");
    }
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

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

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Mitigation Plans</b>
        </span>
      </div>
      <div className="a-content mitigation-print">
        <div className="page-head">
          <div>
            <div className="page-title">Mitigation Plans</div>
            <div className="page-desc">Response plans for register risks scoring ≥ {PLAN_REQUIRED_SCORE}</div>
          </div>
          <button className="btn btn-secondary no-print" onClick={() => window.print()}>
            <DownloadIcon className="icon" /> Print
          </button>
        </div>

        {rows.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              No risks need a mitigation plan yet. Add risks in the Risk Register.
            </p>
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: "0.9rem 1.1rem", display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
              <b className="num" style={{ fontSize: "1rem" }}>
                {submittedCount} of {requiredCount} plans submitted
              </b>
              <span className="chip chip-good">{acceptedCount} accepted</span>
              <span className="spacer" style={{ flex: 1 }} />
              <div className="segmented no-print">
                {(["status", "category", "flat"] as Grouping[]).map((g) => (
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
                    {g === "status" ? "By status" : g === "category" ? "By category" : "Flat"}
                  </button>
                ))}
              </div>
            </div>

            {groups.map((group) => (
              <div key={group.key} className="card">
                <div className="card-head">
                  <div className="card-title">{group.label}</div>
                  <div className="card-title-sub">{group.rows.length} risks</div>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Risk</th>
                        <th style={{ textAlign: "center" }}>Score</th>
                        <th>Strategy</th>
                        <th>Plan</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {group.rows.map((r) => {
                        const open = expanded.has(r.id);
                        const canEdit = editableStatus(r.mitigation_status);
                        return (
                          <Fragment key={r.id}>
                            <tr onClick={() => toggle(r.id)} style={{ cursor: "pointer" }}>
                              <td>
                                <div className="subname">{r.title}</div>
                                <div className="actid">{r.code}{r.category ? ` · ${r.category}` : ""}</div>
                              </td>
                              <td className="num" style={{ textAlign: "center" }}>{r.score}</td>
                              <td>{r.mitigation_strategy ?? "—"}</td>
                              <td>
                                <span className={`chip ${MIT_CHIP[r.mitigation_status]}`}>{MIT_LABEL[r.mitigation_status]}</span>
                              </td>
                              <td className="num" style={{ textAlign: "right" }}>{open ? "▾" : "▸"}</td>
                            </tr>
                            {open && (
                              <tr>
                                <td colSpan={5} style={{ background: "var(--surface-2)" }}>
                                  <div style={{ padding: ".6rem .2rem", display: "flex", flexDirection: "column", gap: ".6rem" }}>
                                    {r.description && (
                                      <div style={{ fontSize: ".8125rem", color: "var(--text-muted)" }}>{r.description}</div>
                                    )}
                                    <div style={{ display: "flex", gap: ".5rem", alignItems: "center", flexWrap: "wrap" }}>
                                      <label style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                                        Strategy
                                        <select
                                          value={r.mitigation_strategy ?? ""}
                                          disabled={!canEdit}
                                          onChange={(e) => patchRisk(r.id, { mitigation_strategy: e.target.value || null })}
                                        >
                                          <option value="">—</option>
                                          {STRATEGIES.map((s) => <option key={s} value={s}>{s}</option>)}
                                        </select>
                                      </label>
                                    </div>
                                    <textarea
                                      defaultValue={r.mitigation_summary ?? ""}
                                      placeholder="Response narrative…"
                                      disabled={!canEdit}
                                      className={canEdit ? "field-editable no-print" : "no-print"}
                                      onBlur={(e) =>
                                        e.target.value !== (r.mitigation_summary ?? "") &&
                                        patchRisk(r.id, { mitigation_summary: e.target.value })
                                      }
                                      style={{ width: "100%", minHeight: 44 }}
                                    />
                                    {r.mitigation_summary && !canEdit && (
                                      <div style={{ fontSize: ".8125rem" }}>{r.mitigation_summary}</div>
                                    )}
                                    <ActionItems
                                      basePath={`/projects/${project!.id}/risks/${r.id}`}
                                      items={r.items ?? []}
                                      editable={canEdit}
                                      trackable={r.mitigation_status === "accepted"}
                                      onChanged={load}
                                    />
                                    {r.review_note && r.mitigation_status === "needs_revision" && (
                                      <div className="banner warn"><span className="banner-text">Reviewer: {r.review_note}</span></div>
                                    )}
                                    <div className="no-print" style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
                                      {canEdit && (
                                        <button className="btn btn-primary btn-sm" onClick={() => mitigationAction(r.id, "submit")}>
                                          Submit plan
                                        </button>
                                      )}
                                      {isAdmin && r.mitigation_status === "submitted" && (
                                        <>
                                          <input
                                            placeholder="Review note"
                                            value={reviewNote[r.id] ?? ""}
                                            onChange={(e) => setReviewNote((p) => ({ ...p, [r.id]: e.target.value }))}
                                            style={{ width: 200 }}
                                          />
                                          <button
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => mitigationAction(r.id, "review", { decision: "needs_revision", note: reviewNote[r.id] })}
                                          >
                                            Return for revision
                                          </button>
                                          <button
                                            className="btn btn-primary btn-sm"
                                            onClick={() => mitigationAction(r.id, "review", { decision: "accept", note: reviewNote[r.id] })}
                                          >
                                            Accept plan
                                          </button>
                                        </>
                                      )}
                                    </div>
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
