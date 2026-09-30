"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { PageState } from "@/components/PageShell";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, RiskItem, RiskStatusValue, User, WbsNode } from "@/lib/types";
import { QsraRiskEditor } from "@/components/risk/QsraRiskEditor";

const CATEGORIES = ["Design", "Procurement", "Construction", "Weather", "Commercial", "Permitting", "Interface", "Other"];
const STATUSES: RiskStatusValue[] = ["open", "mitigating", "closed", "occurred"];
const STATUS_CHIP: Record<RiskStatusValue, string> = {
  open: "chip-warn",
  mitigating: "chip-info",
  closed: "chip-good",
  occurred: "chip-crit",
};
const MIT_CHIP: Record<string, string> = {
  none: "chip-neutral",
  draft: "chip-info",
  submitted: "chip-warn",
  accepted: "chip-good",
  needs_revision: "chip-crit",
};

function scoreClass(score: number): string {
  if (score >= 15) return "chip-crit";
  if (score >= 10) return "chip-warn";
  if (score <= 4) return "chip-good";
  return "chip-neutral";
}

export default function RiskRegisterPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [draft, setDraft] = useState({ title: "", description: "", category: "", probability: 3, impact: 3 });
  // Loaded once, the first time a row is opened: the QSRA editor links risks
  // to activities / WBS nodes of the live programme.
  const [activities, setActivities] = useState<Activity[] | null>(null);
  const [wbsNodes, setWbsNodes] = useState<WbsNode[]>([]);

  useEffect(() => {
    if (!expanded || !project || activities !== null) return;
    Promise.all([
      api.get<Activity[]>(`/activities?project_id=${project.id}`),
      api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`).catch(() => [] as WbsNode[]),
    ])
      .then(([acts, nodes]) => {
        setActivities(acts);
        setWbsNodes(nodes);
      })
      .catch(() => setActivities([]));
  }, [expanded, project, activities]);

  useEffect(() => {
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
      setRisks(await api.get<RiskItem[]>(`/projects/${project.id}/risks`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the risk register.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  const isAdmin = me?.role === "company_admin";

  async function createRisk() {
    if (!project || !draft.title.trim()) return;
    try {
      await api.post(`/projects/${project.id}/risks`, {
        title: draft.title.trim(),
        description: draft.description || null,
        category: draft.category || null,
        probability: draft.probability,
        impact: draft.impact,
      });
      setDraft({ title: "", description: "", category: "", probability: 3, impact: 3 });
      setNewOpen(false);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not create the risk.", "error");
    }
  }

  async function patchRisk(id: string, body: Record<string, unknown>) {
    if (!project) return;
    try {
      const updated = await api.patch<RiskItem>(`/projects/${project.id}/risks/${id}`, body);
      setRisks((prev) => prev.map((r) => (r.id === id ? { ...r, ...updated } : r)));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Update failed.", "error");
    }
  }

  async function deleteRisk(id: string) {
    if (!project) return;
    try {
      await api.delete(`/projects/${project.id}/risks/${id}`);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete.", "error");
    }
  }

  if (loading) {
    return <PageState kind="loading" section="Risk" title="Risk Register" />;
  }
  if (error) {
    return <PageState kind="error" section="Risk" title="Risk Register" message={error} />;
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Risk
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Risk Register</div>
            <div className="page-desc">
              {risks.length} risks · probability × impact scored 1–25 · {risks.filter((r) => r.qsra_enabled).length}{" "}
              quantified for <Link href="/risk">QSRA</Link>
            </div>
          </div>
          <button className="btn btn-primary" onClick={() => setNewOpen((v) => !v)}>
            + New risk
          </button>
        </div>

        {newOpen && (
          <div className="card" style={{ padding: "1rem 1.1rem", display: "flex", flexDirection: "column", gap: ".6rem" }}>
            <input
              placeholder="Risk title"
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
            <textarea
              placeholder="Description (optional)"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              style={{ minHeight: 44 }}
            />
            <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap" }}>
              <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
                <option value="">Category…</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <label style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                Probability
                <select value={draft.probability} onChange={(e) => setDraft({ ...draft, probability: Number(e.target.value) })}>
                  {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <label style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                Impact
                <select value={draft.impact} onChange={(e) => setDraft({ ...draft, impact: Number(e.target.value) })}>
                  {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <button className="btn btn-primary btn-sm" disabled={!draft.title.trim()} onClick={createRisk}>
                Create
              </button>
            </div>
          </div>
        )}

        {risks.length === 0 ? (
          <div className="card">
            <p className="empty-state">No risks logged yet.</p>
          </div>
        ) : (
          <div className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Risk</th>
                    <th style={{ textAlign: "center" }}>P</th>
                    <th style={{ textAlign: "center" }}>I</th>
                    <th style={{ textAlign: "center" }}>Score</th>
                    <th>Status</th>
                    <th>Owner</th>
                    <th>QSRA</th>
                    <th>Mitigation</th>
                  </tr>
                </thead>
                <tbody>
                  {risks.map((r) => (
                    <Fragment key={r.id}>
                      <tr onClick={() => setExpanded(expanded === r.id ? null : r.id)} style={{ cursor: "pointer" }}>
                        <td className="mono">{r.code}</td>
                        <td>
                          <div className="subname">{r.title}</div>
                          {r.category && <div className="actid">{r.category}</div>}
                        </td>
                        <td className="num" style={{ textAlign: "center" }}>{r.probability}</td>
                        <td className="num" style={{ textAlign: "center" }}>{r.impact}</td>
                        <td style={{ textAlign: "center" }}>
                          <span className={`chip ${scoreClass(r.score)}`}>{r.score}</span>
                        </td>
                        <td><span className={`chip ${STATUS_CHIP[r.status]}`}>{r.status}</span></td>
                        <td>{r.owner_name ?? "—"}</td>
                        <td className="num" style={{ fontSize: ".75rem" }}>
                          {r.qsra_enabled ? (
                            <>
                              {r.probability_pct ?? `~${[5, 20, 40, 60, 85][r.probability - 1]}`}% ·{" "}
                              {r.impact_ml ?? r.impact_max ?? "—"}
                              {r.impact_mode === "duration_pct" ? "%" : " d"}
                              <div className="actid">
                                {r.apply_to_wbs ? "WBS" : `${r.activity_external_ids.length} act.`}
                                {r.risk_kind === "opportunity" ? " · opportunity" : ""}
                              </div>
                            </>
                          ) : (
                            <span className="actid">Not quantified</span>
                          )}
                        </td>
                        <td><span className={`chip ${MIT_CHIP[r.mitigation_status]}`}>{r.mitigation_status.replace("_", " ")}</span></td>
                      </tr>
                      {expanded === r.id && (
                        <tr>
                          <td colSpan={9} style={{ background: "var(--surface-2)" }}>
                            <div style={{ padding: ".7rem .3rem", display: "flex", flexDirection: "column", gap: ".5rem" }}>
                              <textarea
                                defaultValue={r.description ?? ""}
                                placeholder="Description"
                                className="field-editable"
                                onBlur={(e) => e.target.value !== (r.description ?? "") && patchRisk(r.id, { description: e.target.value })}
                                style={{ width: "100%", minHeight: 44 }}
                              />
                              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center" }}>
                                <input
                                  defaultValue={r.owner_name ?? ""}
                                  placeholder="Owner"
                                  className="field-editable"
                                  onBlur={(e) => e.target.value !== (r.owner_name ?? "") && patchRisk(r.id, { owner_name: e.target.value || null })}
                                  style={{ width: 160 }}
                                />
                                <label style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                                  P
                                  <select value={r.probability} onChange={(e) => patchRisk(r.id, { probability: Number(e.target.value) })}>
                                    {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                                  </select>
                                </label>
                                <label style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                                  I
                                  <select value={r.impact} onChange={(e) => patchRisk(r.id, { impact: Number(e.target.value) })}>
                                    {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                                  </select>
                                </label>
                                <label style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                                  Status
                                  <select value={r.status} onChange={(e) => patchRisk(r.id, { status: e.target.value })}>
                                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                                  </select>
                                </label>
                                <select
                                  value={r.category ?? ""}
                                  onChange={(e) => patchRisk(r.id, { category: e.target.value || null })}
                                >
                                  <option value="">Category…</option>
                                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                                </select>
                              </div>
                              {activities === null ? (
                                <p className="page-desc">Loading the schedule…</p>
                              ) : (
                                <QsraRiskEditor
                                  risk={r}
                                  activities={activities}
                                  wbsNodes={wbsNodes}
                                  onPatch={(body) => patchRisk(r.id, body)}
                                />
                              )}
                              <div style={{ display: "flex", gap: ".5rem" }}>
                                <Link href="/risk/mitigation-plans" className="btn btn-secondary btn-sm">
                                  Open mitigation plan →
                                </Link>
                                {isAdmin && (
                                  <button className="btn btn-ghost btn-sm" onClick={() => deleteRisk(r.id)}>
                                    Delete risk
                                  </button>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
