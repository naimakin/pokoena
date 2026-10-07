"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import { ChevronDownIcon, ChevronRightIcon, LayersIcon, PencilIcon, TrashIcon } from "@/components/icons";
import type {
  ActivityCodes,
  ProjectScope,
  ScopePreview,
  ScopeRulePayload,
  SubcontractorOrg,
  WbsNode,
} from "@/lib/types";

const selectStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  padding: ".5rem .65rem",
  fontSize: ".8125rem",
};

interface Draft {
  id: string | null;
  name: string;
  discipline: string;
  orgId: string;
  wbsIds: string[];
  codeIds: string[];
}

const EMPTY_DRAFT: Draft = { id: null, name: "", discipline: "", orgId: "", wbsIds: [], codeIds: [] };

/** Administration → Subcontractor scopes: the slice of the programme each
 *  subcontractor sees, named by WBS (with its subtree) and/or activity code
 *  values. Rules are stored as P6 ids and re-applied after every programme
 *  upload (backend: services/scope_rules.py). */
export default function ScopesPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [scopes, setScopes] = useState<ProjectScope[]>([]);
  const [wbs, setWbs] = useState<WbsNode[]>([]);
  const [codes, setCodes] = useState<ActivityCodes | null>(null);
  const [orgs, setOrgs] = useState<SubcontractorOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);

  async function load(projectId: string) {
    setLoading(true);
    setError(null);
    try {
      const [scopeList, wbsList, codeData, orgList] = await Promise.all([
        api.get<ProjectScope[]>(`/projects/${projectId}/scopes`),
        api.get<WbsNode[]>(`/projects/${projectId}/wbs-nodes`),
        api.get<ActivityCodes>(`/projects/${projectId}/activity-codes`),
        api.get<SubcontractorOrg[]>("/subcontractor-organizations"),
      ]);
      setScopes(scopeList);
      setWbs(wbsList);
      setCodes(codeData);
      setOrgs(orgList);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load scopes.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (project) load(project.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  const wbsLabel = useMemo(() => new Map(wbs.map((n) => [n.wbs_id, n.wbs_short_name || n.wbs_name])), [wbs]);
  const codeLabel = useMemo(() => {
    const typeName = new Map((codes?.code_types ?? []).map((t) => [t.id, t.name]));
    return new Map(
      (codes?.code_values ?? []).map((v) => [v.actv_code_id, `${typeName.get(v.code_type_id) ?? "Code"}: ${v.short_name || v.name}`]),
    );
  }, [codes]);
  const orgName = useMemo(() => new Map(orgs.map((o) => [o.id, o.name])), [orgs]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!project || !draft) return;
    setSaving(true);
    const body = {
      name: draft.name.trim(),
      discipline: draft.discipline.trim() || "General",
      subcontractor_org_id: draft.orgId || null,
      wbs_ids: draft.wbsIds,
      code_value_ids: draft.codeIds,
    };
    try {
      const saved = draft.id
        ? await api.patch<ProjectScope>(`/projects/${project.id}/scopes/${draft.id}`, body)
        : await api.post<ProjectScope>(`/projects/${project.id}/scopes`, body);
      showToast(`${saved.name}: ${saved.activity_count} activities`);
      setDraft(null);
      load(project.id);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save the scope.", "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(scope: ProjectScope) {
    if (!project) return;
    const who = scope.member_count ? ` ${scope.member_count} subcontractor(s) will lose access to it.` : "";
    if (!window.confirm(`Delete scope "${scope.name}"?${who}`)) return;
    try {
      await api.delete(`/projects/${project.id}/scopes/${scope.id}`);
      showToast(`Deleted ${scope.name}`);
      load(project.id);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to delete the scope.", "error");
    }
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">Administration</span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Subcontractor scopes</div>
            <div className="page-desc">
              A scope is the part of the programme a subcontractor sees and updates. Pick it by WBS (each with
              everything under it) and/or activity codes — it follows the programme through every upload. Assign
              scopes to people on <Link href="/user-management">Users</Link>.
            </div>
          </div>
        </div>

        {!project && <p className="empty-state">Select a project to manage its scopes.</p>}

        {project && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Scopes in {project.code}</div>
                <div className="card-title-sub">
                  {scopes.length} {scopes.length === 1 ? "scope" : "scopes"}
                </div>
              </div>
              <button className="btn btn-primary btn-sm" onClick={() => setDraft({ ...EMPTY_DRAFT })} disabled={loading}>
                <LayersIcon className="icon" /> New scope
              </button>
            </div>

            {loading && <p className="empty-state">Loading…</p>}
            {error && (
              <p className="login-error" style={{ margin: "1rem 1.1rem" }}>
                {error}
              </p>
            )}
            {!loading && !error && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Scope</th>
                      <th>Organization</th>
                      <th>Rule</th>
                      <th style={{ textAlign: "right" }}>Activities</th>
                      <th style={{ textAlign: "right" }}>Subcontractors</th>
                      <th style={{ width: 80 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {scopes.length === 0 && (
                      <tr>
                        <td colSpan={6} className="empty-state">
                          No scopes yet. Create one for each subcontractor package — e.g. the MEP WBS of Building A.
                        </td>
                      </tr>
                    )}
                    {scopes.map((s) => {
                      const rule = [
                        ...s.wbs_ids.map((id) => `WBS: ${wbsLabel.get(id) ?? id}`),
                        ...s.code_value_ids.map((id) => codeLabel.get(id) ?? id),
                      ];
                      return (
                        <tr key={s.id}>
                          <td>
                            <div className="subname">{s.name}</div>
                            <div className="cell-sub">{s.discipline}</div>
                          </td>
                          <td>{s.subcontractor_org_id ? (orgName.get(s.subcontractor_org_id) ?? "—") : "—"}</td>
                          <td>
                            {rule.length === 0 ? (
                              <span className="cell-sub">No rule</span>
                            ) : (
                              <div className="role-wrap" style={{ maxWidth: 420 }}>
                                {rule.slice(0, 4).map((r) => (
                                  <span key={r} className="role-badge">
                                    {r}
                                  </span>
                                ))}
                                {rule.length > 4 && (
                                  <span className="role-badge overflow" title={rule.slice(4).join(", ")}>
                                    +{rule.length - 4}
                                  </span>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="num mono">{s.activity_count}</td>
                          <td className="num mono">
                            {s.member_count || <span className="chip chip-warn">None</span>}
                          </td>
                          <td>
                            <div className="actions">
                              <button
                                className="act-btn"
                                title="Edit"
                                aria-label={`Edit ${s.name}`}
                                onClick={() =>
                                  setDraft({
                                    id: s.id,
                                    name: s.name,
                                    discipline: s.discipline,
                                    orgId: s.subcontractor_org_id ?? "",
                                    wbsIds: s.wbs_ids,
                                    codeIds: s.code_value_ids,
                                  })
                                }
                              >
                                <PencilIcon className="icon" />
                              </button>
                              <button
                                className="act-btn act-reject"
                                title="Delete"
                                aria-label={`Delete ${s.name}`}
                                onClick={() => handleDelete(s)}
                              >
                                <TrashIcon className="icon" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {draft && project && (
        <ScopeEditor
          projectId={project.id}
          draft={draft}
          setDraft={setDraft}
          wbs={wbs}
          codes={codes}
          orgs={orgs}
          saving={saving}
          onSave={handleSave}
        />
      )}
    </>
  );
}

function ScopeEditor({
  projectId,
  draft,
  setDraft,
  wbs,
  codes,
  orgs,
  saving,
  onSave,
}: {
  projectId: string;
  draft: Draft;
  setDraft: (d: Draft | null) => void;
  wbs: WbsNode[];
  codes: ActivityCodes | null;
  orgs: SubcontractorOrg[];
  saving: boolean;
  onSave: (e: FormEvent) => void;
}) {
  const [tab, setTab] = useState<"wbs" | "codes">(draft.codeIds.length && !draft.wbsIds.length ? "codes" : "wbs");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<ScopePreview | null>(null);
  const [previewing, setPreviewing] = useState(false);

  // WBS: collapsed below level 2 to start, except the way down to what's selected.
  const hasChildren = useMemo(() => new Set(wbs.map((n) => n.parent_wbs_id).filter(Boolean) as string[]), [wbs]);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => {
    const open = new Set<string>();
    for (const n of wbs) if (draft.wbsIds.includes(n.wbs_id)) n.path_ids.forEach((p) => open.add(p));
    return new Set(wbs.filter((n) => n.depth >= 1 && !open.has(n.wbs_id)).map((n) => n.wbs_id));
  });

  const selectedWbs = useMemo(() => new Set(draft.wbsIds), [draft.wbsIds]);
  const wbsByWbsId = useMemo(() => new Map(wbs.map((n) => [n.wbs_id, n])), [wbs]);
  // A node is implied by a selected ancestor (its whole subtree is in).
  const impliedBy = (n: WbsNode) => n.path_ids.slice(0, -1).find((id) => selectedWbs.has(id) && id !== n.wbs_id);

  const q = query.trim().toLowerCase();
  const visibleWbs = useMemo(() => {
    if (q) {
      return wbs.filter((n) => `${n.wbs_short_name} ${n.wbs_name} ${n.outline_code}`.toLowerCase().includes(q));
    }
    return wbs.filter((n) => !n.path_ids.slice(0, -1).some((id) => collapsed.has(id)));
  }, [wbs, q, collapsed]);

  const codeGroups = useMemo(() => {
    if (!codes) return [];
    return codes.code_types
      .map((t) => ({
        type: t,
        values: codes.code_values
          .filter((v) => v.code_type_id === t.id)
          .filter((v) => !q || `${v.short_name ?? ""} ${v.name}`.toLowerCase().includes(q))
          .map((v) => ({ value: v, count: codes.assignments[v.id]?.length ?? 0 })),
      }))
      .filter((g) => g.values.length > 0);
  }, [codes, q]);

  const rule: ScopeRulePayload = { wbs_ids: draft.wbsIds, code_value_ids: draft.codeIds };
  const ruleKey = JSON.stringify(rule);
  useEffect(() => {
    if (!draft.wbsIds.length && !draft.codeIds.length) {
      setPreview(null);
      return;
    }
    setPreviewing(true);
    const timer = window.setTimeout(() => {
      const suffix = draft.id ? `?scope_id=${draft.id}` : "";
      api
        .post<ScopePreview>(`/projects/${projectId}/scopes/preview${suffix}`, rule)
        .then(setPreview)
        .catch(() => setPreview(null))
        .finally(() => setPreviewing(false));
    }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruleKey, projectId, draft.id]);

  function toggleWbs(id: string) {
    setDraft({ ...draft, wbsIds: selectedWbs.has(id) ? draft.wbsIds.filter((w) => w !== id) : [...draft.wbsIds, id] });
  }

  function toggleCode(id: string) {
    setDraft({
      ...draft,
      codeIds: draft.codeIds.includes(id) ? draft.codeIds.filter((c) => c !== id) : [...draft.codeIds, id],
    });
  }

  function toggleCollapsed(id: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const codeName = (id: string) => {
    const v = codes?.code_values.find((c) => c.actv_code_id === id);
    return v ? v.short_name || v.name : id;
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setDraft(null)}>
      <form className="modal-lg" onSubmit={onSave} role="dialog" aria-modal="true" aria-labelledby="scope-editor-title">
        <div className="modal-head">
          <div>
            <div className="modal-title" id="scope-editor-title">
              {draft.id ? `Edit ${draft.name}` : "New scope"}
            </div>
            <div className="modal-desc">
              Activities under any selected WBS, and carrying the selected codes (any value of a code type; every type
              you use).
            </div>
          </div>
        </div>

        <div className="modal-body scope-editor">
          <div className="form-row">
            <div className="field">
              <label htmlFor="scope-name">Name</label>
              <input
                type="text"
                id="scope-name"
                required
                value={draft.name}
                placeholder="e.g. Building A — MEP"
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="scope-discipline">Discipline</label>
              <input
                type="text"
                id="scope-discipline"
                value={draft.discipline}
                placeholder="General"
                onChange={(e) => setDraft({ ...draft, discipline: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="scope-org">Organization</label>
              <select
                id="scope-org"
                value={draft.orgId}
                onChange={(e) => setDraft({ ...draft, orgId: e.target.value })}
                style={selectStyle}
              >
                <option value="">None</option>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="scope-grid">
            <section className="scope-pick" aria-label="Rule">
              <div className="scope-pick-head">
                <div className="segmented">
                  <button type="button" className={tab === "wbs" ? "active" : ""} onClick={() => setTab("wbs")}>
                    WBS{draft.wbsIds.length ? ` · ${draft.wbsIds.length}` : ""}
                  </button>
                  <button type="button" className={tab === "codes" ? "active" : ""} onClick={() => setTab("codes")}>
                    Activity codes{draft.codeIds.length ? ` · ${draft.codeIds.length}` : ""}
                  </button>
                </div>
                <div className="field scope-search">
                  <input
                    type="text"
                    placeholder={tab === "wbs" ? "Find a WBS…" : "Find a code value…"}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    aria-label="Filter"
                  />
                </div>
              </div>

              <div className="scope-list">
                {tab === "wbs" && wbs.length === 0 && (
                  <p className="empty-state">This project has no WBS yet — upload a programme first.</p>
                )}
                {tab === "wbs" &&
                  visibleWbs.map((n) => {
                    const implied = impliedBy(n);
                    const checked = selectedWbs.has(n.wbs_id) || Boolean(implied);
                    return (
                      <div
                        key={n.wbs_id}
                        className={`scope-row${checked ? " is-on" : ""}`}
                        style={{ paddingLeft: `${(q ? 0 : n.depth) * 16 + 6}px` }}
                      >
                        {!q && hasChildren.has(n.wbs_id) ? (
                          <button
                            type="button"
                            className="scope-twisty"
                            aria-label={collapsed.has(n.wbs_id) ? `Expand ${n.wbs_short_name}` : `Collapse ${n.wbs_short_name}`}
                            aria-expanded={!collapsed.has(n.wbs_id)}
                            onClick={() => toggleCollapsed(n.wbs_id)}
                          >
                            {collapsed.has(n.wbs_id) ? <ChevronRightIcon className="icon" /> : <ChevronDownIcon className="icon" />}
                          </button>
                        ) : (
                          <span className="scope-twisty" aria-hidden="true" />
                        )}
                        <label title={implied ? `Included with ${wbsByWbsId.get(implied)?.wbs_short_name}` : undefined}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={Boolean(implied)}
                            onChange={() => toggleWbs(n.wbs_id)}
                          />
                          <span className="mono scope-code">{n.wbs_short_name}</span>
                          <span className="scope-name">{n.wbs_name}</span>
                        </label>
                        <span className="scope-count mono">{n.total_activity_count}</span>
                      </div>
                    );
                  })}

                {tab === "codes" && codeGroups.length === 0 && (
                  <p className="empty-state">{q ? "No code value matches." : "This programme has no activity codes."}</p>
                )}
                {tab === "codes" &&
                  codeGroups.map((g) => (
                    <div key={g.type.id} className="scope-code-group">
                      <div className="scope-group-label">{g.type.name}</div>
                      {g.values.map(({ value, count }) => (
                        <div key={value.id} className={`scope-row${draft.codeIds.includes(value.actv_code_id) ? " is-on" : ""}`}>
                          <span className="scope-twisty" aria-hidden="true" />
                          <label>
                            <input
                              type="checkbox"
                              checked={draft.codeIds.includes(value.actv_code_id)}
                              onChange={() => toggleCode(value.actv_code_id)}
                            />
                            {value.short_name && <span className="mono scope-code">{value.short_name}</span>}
                            <span className="scope-name">{value.name}</span>
                          </label>
                          <span className="scope-count mono">{count}</span>
                        </div>
                      ))}
                    </div>
                  ))}
              </div>
            </section>

            <aside className="scope-preview" aria-live="polite">
              <div className="scope-preview-label">Selected</div>
              {draft.wbsIds.length + draft.codeIds.length === 0 ? (
                <p className="cell-sub">Nothing yet — tick WBS nodes or code values.</p>
              ) : (
                <div className="pick-wrap">
                  {draft.wbsIds.map((id) => (
                    <button type="button" key={`w-${id}`} className="pick-chip selected" onClick={() => toggleWbs(id)} title="Remove">
                      WBS {wbsByWbsId.get(id)?.wbs_short_name ?? id} ×
                    </button>
                  ))}
                  {draft.codeIds.map((id) => (
                    <button type="button" key={`c-${id}`} className="pick-chip selected" onClick={() => toggleCode(id)} title="Remove">
                      {codeName(id)} ×
                    </button>
                  ))}
                </div>
              )}

              <div className="scope-preview-label">Matches</div>
              {preview ? (
                <>
                  <div className="scope-preview-count">
                    <span className="mono">{preview.count}</span> activities{previewing ? "…" : ""}
                  </div>
                  {preview.claimed_elsewhere > 0 && (
                    <div className="banner warn" style={{ padding: ".5rem .65rem" }}>
                      <span className="banner-text" style={{ color: "inherit" }}>
                        {preview.claimed_elsewhere} of these already belong to an older scope and stay there.
                      </span>
                    </div>
                  )}
                  <ul className="scope-sample">
                    {preview.sample.map((a) => (
                      <li key={a.external_id}>
                        <span className="mono">{a.external_id}</span> {a.name}
                      </li>
                    ))}
                    {preview.count > preview.sample.length && (
                      <li className="cell-sub">and {preview.count - preview.sample.length} more</li>
                    )}
                  </ul>
                </>
              ) : (
                <p className="cell-sub">{previewing ? "Counting…" : "—"}</p>
              )}
            </aside>
          </div>
        </div>

        <div className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={() => setDraft(null)}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            type="submit"
            disabled={saving || !draft.name.trim() || draft.wbsIds.length + draft.codeIds.length === 0}
          >
            {saving ? "Saving…" : draft.id ? "Save scope" : "Create scope"}
          </button>
        </div>
      </form>
    </div>
  );
}
