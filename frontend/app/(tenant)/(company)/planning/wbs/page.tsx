"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { WbsNode } from "@/lib/types";
import { ChevronDownIcon } from "@/components/icons";

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

export default function WbsPage() {
  const { project } = useProjectContext();
  const [nodes, setNodes] = useState<WbsNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  useEffect(() => {
    async function load() {
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
        setCollapsed(new Set());
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load the WBS.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [project]);

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
          {nodes.length > 0 && (
            <div style={{ display: "flex", gap: ".55rem" }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setCollapsed(new Set())}>
                Expand all
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setCollapsed(new Set(parentIds))}
              >
                Collapse all
              </button>
            </div>
          )}
        </div>

        <div className="card">
          {nodes.length === 0 ? (
            <p className="empty-state">
              No WBS imported yet. Upload a P6 <span className="mono">.xer</span> schedule from Planning &rsaquo;
              Program Library — its PROJWBS structure loads here automatically.
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>WBS Code</th>
                    <th>WBS Name</th>
                    <th style={{ textAlign: "right" }}>Total Activities</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((node) => {
                    const hasChildren = node.children.length > 0;
                    const isCollapsed = collapsed.has(node.wbs_id);
                    return (
                      <tr key={node.id}>
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
                            <span className="mono" style={{ fontSize: ".75rem" }}>
                              {node.wbs_short_name || "—"}
                            </span>
                          </div>
                        </td>
                        <td style={{ fontWeight: hasChildren ? 600 : 400 }}>{node.wbs_name}</td>
                        <td className="num" style={{ textAlign: "right" }}>
                          {node.total_activity_count.toLocaleString()}
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
