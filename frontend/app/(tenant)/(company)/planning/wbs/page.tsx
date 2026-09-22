"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { ScheduleImport, WbsNode } from "@/lib/types";
import { ChevronDownIcon, EyeIcon, EyeOffIcon, XIcon } from "@/components/icons";

interface TreeNode extends WbsNode {
  children: TreeNode[];
  depth: number;
}

function buildTree(nodes: WbsNode[]): TreeNode[] {
  const byId = new Map<string, TreeNode>();
  for (const n of nodes) byId.set(n.wbs_id, { ...n, children: [], depth: 0 });

  const roots: TreeNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parent_wbs_id ? byId.get(node.parent_wbs_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }

  const setDepth = (n: TreeNode, d: number) => {
    n.depth = d;
    for (const c of n.children) setDepth(c, d + 1);
  };
  for (const r of roots) setDepth(r, 0);
  return roots;
}

function flatten(roots: TreeNode[], collapsed: Set<string>): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      out.push(n);
      if (n.children.length > 0 && !collapsed.has(n.wbs_id)) walk(n.children);
    }
  };
  walk(roots);
  return out;
}

// Every node regardless of collapse state — used to size the "Collapse to level"
// list and to compute which nodes fall at or past a chosen level.
function flattenAll(roots: TreeNode[]): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      out.push(n);
      walk(n.children);
    }
  };
  walk(roots);
  return out;
}

const selectStyle: CSSProperties = {
  fontSize: ".75rem",
  height: 30,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(-2)}`;
}

const EMPTY_DRAFT = { parentWbsId: "", shortName: "", name: "" };

export default function WbsPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [nodes, setNodes] = useState<WbsNode[]>([]);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  // Which uploaded program's WBS to show. Defaults to the current update once
  // the import list loads; null only while nothing has loaded yet.
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nodesLoading, setNodesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [newOpen, setNewOpen] = useState(false);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [hiddenRoots, setHiddenRoots] = useState<WbsNode[]>([]);
  const [hiddenOpen, setHiddenOpen] = useState(false);
  const [hidingId, setHidingId] = useState<string | null>(null);

  const loadImports = useCallback(async () => {
    if (!project) {
      setImports([]);
      setSelectedImportId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`);
      setImports(list);
      setSelectedImportId((prev) => {
        if (prev && list.some((i) => i.id === prev)) return prev;
        return (list.find((i) => i.is_current) ?? list[0])?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the schedule imports.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    loadImports();
  }, [loadImports]);

  const currentImportId = useMemo(() => (imports.find((i) => i.is_current) ?? imports[0])?.id ?? null, [imports]);
  const selectedImport = useMemo(() => imports.find((i) => i.id === selectedImportId) ?? null, [imports, selectedImportId]);
  // Program Library edits only ever touch the live schedule, so Add/Delete only
  // make sense while viewing it — a historical program's tree is read-only.
  const isViewingCurrent = selectedImportId !== null && selectedImportId === currentImportId;

  const loadNodes = useCallback(async () => {
    if (!project || !selectedImportId) {
      setNodes([]);
      return;
    }
    setNodesLoading(true);
    try {
      const path =
        selectedImportId === currentImportId
          ? `/projects/${project.id}/wbs-nodes`
          : `/projects/${project.id}/schedule-imports/${selectedImportId}/wbs-nodes`;
      const rows = await api.get<WbsNode[]>(path);
      setNodes(rows);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to load this program's WBS.");
      setNodes([]);
    } finally {
      setNodesLoading(false);
    }
  }, [project, selectedImportId, currentImportId, showToast]);

  // Roots hidden from the live tree (see hideRoot below) — only meaningful
  // while viewing the current update, since a historical program's tree never
  // has anything hidden from it.
  const loadHiddenRoots = useCallback(async () => {
    if (!project || !isViewingCurrent) {
      setHiddenRoots([]);
      return;
    }
    try {
      setHiddenRoots(await api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes/hidden`));
    } catch {
      setHiddenRoots([]);
    }
  }, [project, isViewingCurrent]);

  useEffect(() => {
    loadNodes();
    setCollapsed(new Set());
    setNewOpen(false);
    setDraft(EMPTY_DRAFT);
  }, [loadNodes]);

  useEffect(() => {
    loadHiddenRoots();
    setHiddenOpen(false);
  }, [loadHiddenRoots]);

  const roots = useMemo(() => buildTree(nodes), [nodes]);
  const allNodes = useMemo(() => flattenAll(roots), [roots]);
  const visible = useMemo(() => flatten(roots, collapsed), [roots, collapsed]);
  const parentIds = useMemo(
    () => new Set(nodes.filter((n) => nodes.some((m) => m.parent_wbs_id === n.wbs_id)).map((n) => n.wbs_id)),
    [nodes],
  );
  // Root nodes' totals sum to the whole program — every activity is under some WBS.
  const totalActivities = useMemo(() => roots.reduce((sum, r) => sum + r.total_activity_count, 0), [roots]);
  const maxLevel = useMemo(() => (allNodes.length ? Math.max(...allNodes.map((n) => n.depth)) + 1 : 1), [allNodes]);

  function toggle(wbsId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
  }

  // "Collapse to Level N" (matches P6's Group and Sort dialog): levels 1..N stay
  // expanded, everything at level N and deeper collapses under its level-N parent.
  function collapseToLevel(level: number) {
    setCollapsed(
      new Set(allNodes.filter((n) => n.children.length > 0 && n.depth + 1 >= level).map((n) => n.wbs_id)),
    );
  }

  async function createNode() {
    if (!project || !draft.name.trim()) return;
    setSaving(true);
    try {
      await api.post(`/projects/${project.id}/wbs-nodes`, {
        parent_wbs_id: draft.parentWbsId || null,
        wbs_short_name: draft.shortName.trim() || draft.name.trim(),
        wbs_name: draft.name.trim(),
      });
      setDraft(EMPTY_DRAFT);
      setNewOpen(false);
      await loadNodes();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not create the WBS node.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteNode(node: TreeNode) {
    if (!project) return;
    if (!window.confirm(`Delete WBS node "${node.wbs_name}"? This can't be undone.`)) return;
    try {
      await api.delete(`/projects/${project.id}/wbs-nodes/${node.id}`);
      await loadNodes();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete the WBS node.");
    }
  }

  // Hides a whole root program from this view without touching its data — for
  // a project that already had two unrelated programs' WBS mixed together
  // before imports started replacing this table wholesale, this is how you
  // tell Poko which one to stop showing. Reversible any time from "Hidden".
  async function hideRoot(node: TreeNode) {
    if (!project) return;
    if (
      !window.confirm(
        `Hide "${node.wbs_name}" from this page? Its activities aren't affected anywhere else — you can unhide it any time from "Hidden" above.`,
      )
    ) {
      return;
    }
    setHidingId(node.id);
    try {
      await api.post(`/projects/${project.id}/wbs-nodes/${node.id}/hide`);
      await Promise.all([loadNodes(), loadHiddenRoots()]);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not hide this WBS node.");
    } finally {
      setHidingId(null);
    }
  }

  async function unhideRoot(node: WbsNode) {
    if (!project) return;
    setHidingId(node.id);
    try {
      await api.post(`/projects/${project.id}/wbs-nodes/${node.id}/unhide`);
      await Promise.all([loadNodes(), loadHiddenRoots()]);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not unhide this WBS node.");
    } finally {
      setHidingId(null);
    }
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
        <p className="login-error" style={{ maxWidth: 420 }}>
          {error}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>WBS</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Work Breakdown Structure</div>
            <div className="page-desc">
              {nodesLoading
                ? "Loading…"
                : nodes.length > 0
                  ? `${totalActivities.toLocaleString()} total activities · ${nodes.length} WBS ${nodes.length === 1 ? "node" : "nodes"}` +
                    (!isViewingCurrent ? " · read-only — showing an earlier program" : "")
                  : "The project's work breakdown structure"}
            </div>
          </div>
          <div style={{ display: "flex", gap: ".55rem", alignItems: "center", flexWrap: "wrap" }}>
            {imports.length > 0 && (
              <label style={{ display: "flex", alignItems: "center", gap: ".4rem", fontSize: ".75rem", color: "var(--text-muted)" }}>
                Program
                <select
                  style={{ ...selectStyle, minWidth: 220 }}
                  value={selectedImportId ?? ""}
                  onChange={(e) => setSelectedImportId(e.target.value)}
                >
                  {imports.map((imp) => (
                    <option key={imp.id} value={imp.id}>
                      {imp.revision_label ?? imp.filename}
                      {imp.data_date ? ` (${fmtDate(imp.data_date)})` : ""}
                      {imp.id === currentImportId ? " — Current update" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {nodes.length > 0 && (
              <>
                <label style={{ display: "flex", alignItems: "center", gap: ".4rem", fontSize: ".75rem", color: "var(--text-muted)" }}>
                  Collapse to
                  <select
                    style={selectStyle}
                    defaultValue=""
                    onChange={(e) => {
                      if (e.target.value) collapseToLevel(Number(e.target.value));
                      e.target.value = "";
                    }}
                  >
                    <option value="" disabled>
                      Level…
                    </option>
                    {Array.from({ length: maxLevel }, (_, i) => i + 1).map((level) => (
                      <option key={level} value={level}>
                        Level {level}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="btn btn-secondary btn-sm" onClick={() => setCollapsed(new Set())}>
                  Expand all
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setCollapsed(new Set(parentIds))}
                >
                  Collapse all
                </button>
              </>
            )}
            {isViewingCurrent && hiddenRoots.length > 0 && (
              <button className="btn btn-secondary btn-sm" onClick={() => setHiddenOpen((v) => !v)}>
                <EyeOffIcon className="icon" /> Hidden ({hiddenRoots.length})
              </button>
            )}
            {isViewingCurrent && (
              <button className="btn btn-primary btn-sm" disabled={!project} onClick={() => setNewOpen((v) => !v)}>
                + Add WBS node
              </button>
            )}
          </div>
        </div>

        {hiddenOpen && hiddenRoots.length > 0 && (
          <div className="card" style={{ padding: ".75rem 1.1rem", display: "flex", flexDirection: "column", gap: ".5rem" }}>
            <div style={{ fontSize: ".75rem", fontWeight: 700, color: "var(--text-secondary)" }}>
              Hidden from this view — activities aren&apos;t affected anywhere else
            </div>
            {hiddenRoots.map((root) => (
              <div
                key={root.id}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: ".75rem", fontSize: ".8125rem" }}
              >
                <span>
                  <span className="mono" style={{ color: "var(--text-muted)", marginRight: ".4rem" }}>
                    {root.wbs_short_name}
                  </span>
                  {root.wbs_name}
                  <span className="wbs-band-roll" style={{ marginLeft: ".5rem" }}>
                    Σ {root.total_activity_count.toLocaleString()}
                  </span>
                </span>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={hidingId === root.id}
                  onClick={() => unhideRoot(root)}
                >
                  <EyeIcon className="icon" /> Unhide
                </button>
              </div>
            ))}
          </div>
        )}

        {!isViewingCurrent && selectedImport && (
          <div className="banner">
            <div className="banner-text">
              Showing <b>{selectedImport.revision_label ?? selectedImport.filename}</b>, an earlier program — read-only.
              Switch <b>Program</b> back to the current update to edit the live WBS.
            </div>
          </div>
        )}

        {newOpen && isViewingCurrent && (
          <div className="card" style={{ padding: "1rem 1.1rem", display: "flex", flexDirection: "column", gap: ".6rem" }}>
            <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap" }}>
              <label style={{ fontSize: ".75rem", display: "flex", flexDirection: "column", gap: ".25rem", flex: "1 1 220px" }}>
                Parent
                <select
                  value={draft.parentWbsId}
                  onChange={(e) => setDraft({ ...draft, parentWbsId: e.target.value })}
                >
                  <option value="">— Root (top level) —</option>
                  {nodes.map((n) => (
                    <option key={n.wbs_id} value={n.wbs_id}>
                      {"—".repeat(n.depth)} {n.outline_code} · {n.wbs_name}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ fontSize: ".75rem", display: "flex", flexDirection: "column", gap: ".25rem", flex: "1 1 140px" }}>
                WBS Code
                <input
                  type="text"
                  className="mono"
                  placeholder="e.g. CONST-2"
                  value={draft.shortName}
                  onChange={(e) => setDraft({ ...draft, shortName: e.target.value })}
                  maxLength={50}
                />
              </label>
              <label style={{ fontSize: ".75rem", display: "flex", flexDirection: "column", gap: ".25rem", flex: "2 1 260px" }}>
                WBS Name
                <input
                  type="text"
                  placeholder="e.g. Substructure"
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  maxLength={255}
                />
              </label>
            </div>
            <div style={{ display: "flex", gap: ".5rem" }}>
              <button className="btn btn-primary btn-sm" disabled={!draft.name.trim() || saving} onClick={createNode}>
                {saving ? "Adding…" : "Add node"}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setNewOpen(false);
                  setDraft(EMPTY_DRAFT);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="card">
          {nodesLoading ? (
            <p className="page-desc" style={{ padding: "1rem 1.1rem" }}>
              Loading…
            </p>
          ) : nodes.length === 0 ? (
            <p className="empty-state">
              {isViewingCurrent ? (
                <>
                  No WBS imported yet. Upload a P6 <span className="mono">.xer</span> schedule from Planning &rsaquo;
                  Program Library — its PROJWBS structure loads here automatically, or add nodes manually above.
                </>
              ) : (
                "This program was imported before WBS history was tracked, so its structure wasn't saved."
              )}
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>WBS Code</th>
                    <th>WBS Name</th>
                    <th style={{ textAlign: "right" }}>Total Activities</th>
                    <th style={{ width: 48 }} />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((node) => {
                    const hasChildren = node.children.length > 0;
                    const isCollapsed = collapsed.has(node.wbs_id);
                    const bandClass = hasChildren ? `wbs-band d${Math.min(node.depth, 4)}` : undefined;
                    return (
                      <tr key={node.id} className={bandClass}>
                        <td>
                          <div
                            className="cell-flex"
                            style={{ paddingLeft: `${node.depth * 1.25}rem`, gap: ".4rem" }}
                          >
                            {hasChildren ? (
                              <button
                                onClick={() => toggle(node.wbs_id)}
                                aria-label={isCollapsed ? "Expand" : "Collapse"}
                                aria-expanded={!isCollapsed}
                                style={{
                                  display: "flex",
                                  color: "var(--text-muted)",
                                  transform: isCollapsed ? "rotate(-90deg)" : "none",
                                  transition: "transform var(--dur-1, 120ms) var(--ease, ease)",
                                }}
                              >
                                <ChevronDownIcon className="icon" />
                              </button>
                            ) : (
                              <span style={{ width: 16, flex: "none" }} />
                            )}
                            {hasChildren && (
                              <span className="wbs-level-chip" title={`WBS level ${node.depth + 1}`}>
                                L{node.depth + 1}
                              </span>
                            )}
                            <span className={hasChildren ? "wbs-band-code" : "mono"} style={hasChildren ? undefined : { fontSize: ".75rem" }}>
                              {node.wbs_short_name || "—"}
                            </span>
                          </div>
                        </td>
                        <td style={{ fontWeight: hasChildren ? 600 : 400 }}>{node.wbs_name}</td>
                        <td style={{ textAlign: "right" }}>
                          {hasChildren ? (
                            <span className="wbs-band-roll">Σ {node.total_activity_count.toLocaleString()}</span>
                          ) : (
                            <span className="num">{node.total_activity_count.toLocaleString()}</span>
                          )}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          {isViewingCurrent && (
                            <div className="actions" style={{ justifyContent: "flex-end" }}>
                              {node.depth === 0 && (
                                <button
                                  className="act-btn act-edit"
                                  title="Hide this program from this view (reversible, nothing is deleted)"
                                  disabled={hidingId === node.id}
                                  onClick={() => hideRoot(node)}
                                >
                                  <EyeOffIcon className="icon" />
                                </button>
                              )}
                              <button
                                className="act-btn act-reject"
                                title="Delete WBS node"
                                onClick={() => deleteNode(node)}
                              >
                                <XIcon className="icon" />
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
