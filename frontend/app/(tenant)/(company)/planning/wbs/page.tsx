"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { WbsNode } from "@/lib/types";
import { ChevronDownIcon, XIcon } from "@/components/icons";

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

const EMPTY_DRAFT = { parentWbsId: "", shortName: "", name: "" };

export default function WbsPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [nodes, setNodes] = useState<WbsNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [newOpen, setNewOpen] = useState(false);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!project) {
      setNodes([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const rows = await api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`);
      setNodes(rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the WBS.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
    setCollapsed(new Set());
  }, [load]);

  const roots = useMemo(() => buildTree(nodes), [nodes]);
  const visible = useMemo(() => flatten(roots, collapsed), [roots, collapsed]);
  const parentIds = useMemo(
    () => new Set(nodes.filter((n) => nodes.some((m) => m.parent_wbs_id === n.wbs_id)).map((n) => n.wbs_id)),
    [nodes],
  );

  function toggle(wbsId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
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
      await load();
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
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete the WBS node.");
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
              {nodes.length > 0
                ? `${nodes.length} WBS ${nodes.length === 1 ? "node" : "nodes"} · imported from the project's P6 schedule`
                : "The project's work breakdown structure"}
            </div>
          </div>
          <div style={{ display: "flex", gap: ".55rem" }}>
            {nodes.length > 0 && (
              <>
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
            <button className="btn btn-primary btn-sm" disabled={!project} onClick={() => setNewOpen((v) => !v)}>
              + Add WBS node
            </button>
          </div>
        </div>

        {newOpen && (
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
          {nodes.length === 0 ? (
            <p className="empty-state">
              No WBS imported yet. Upload a P6 <span className="mono">.xer</span> schedule from Planning &rsaquo;
              Program Library — its PROJWBS structure loads here automatically, or add nodes manually above.
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
                          <div className="actions" style={{ justifyContent: "flex-end" }}>
                            <button
                              className="act-btn act-reject"
                              title="Delete WBS node"
                              onClick={() => deleteNode(node)}
                            >
                              <XIcon className="icon" />
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
      </div>
    </>
  );
}
