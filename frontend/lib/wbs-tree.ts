// Shared WBS helpers. The backend (`GET /projects/:id/wbs-nodes`) now returns
// nodes in preorder with `depth`, `path_ids` and a dotted `outline_code`, so the
// frontend only needs to interleave activities, apply collapse, and roll up.

import { displayFinish, displayStart } from "@/lib/schedule-dates";
import type { Activity, WbsNode } from "@/lib/types";

export const UNGROUPED_KEY = "__ungrouped__";

export interface BandRow {
  kind: "band";
  key: string;
  node: WbsNode | null; // null = the synthetic "Ungrouped" band
  label: string;
  outlineCode: string;
  depth: number;
  wbsId: string;
  collapsed: boolean;
  hasChildren: boolean;
  // rollup over the *filtered* activity set in this node's whole subtree
  total: number;
  inProgress: number;
  completed: number;
  avgPercent: number;
  // Earliest start / latest finish across that same subtree (ISO day strings,
  // so plain string compare is a date compare). Used by Planning > Schedule to
  // draw a summary bar on the band row; other consumers ignore them.
  spanStart: string | null;
  spanFinish: string | null;
}

export interface ActivityRow {
  kind: "activity";
  key: string;
  activity: Activity;
  depth: number;
}

export type GridRow = BandRow | ActivityRow;

/** Group a (already filtered) activity list by the WBS node it hangs off. */
export function groupByLeaf(activities: Activity[], knownWbsIds: Set<string>): Map<string, Activity[]> {
  const byLeaf = new Map<string, Activity[]>();
  for (const a of activities) {
    const key = a.wbs_path && knownWbsIds.has(a.wbs_path) ? a.wbs_path : UNGROUPED_KEY;
    const list = byLeaf.get(key);
    if (list) list.push(a);
    else byLeaf.set(key, [a]);
  }
  for (const list of byLeaf.values()) {
    list.sort((x, y) => x.external_id.localeCompare(y.external_id, undefined, { numeric: true }));
  }
  return byLeaf;
}

function rollup(activities: Activity[]) {
  let inProgress = 0;
  let completed = 0;
  let pctSum = 0;
  let spanStart: string | null = null;
  let spanFinish: string | null = null;
  for (const a of activities) {
    if (a.status === "in_progress") inProgress += 1;
    else if (a.status === "complete") completed += 1;
    pctSum += a.percent_complete ?? 0;
    // The same Start/Finish the activity rows show (lib/schedule-dates.ts); a
    // milestone's one date bounds the span on both sides.
    const s = displayStart(a) ?? displayFinish(a);
    const f = displayFinish(a) ?? displayStart(a);
    if (s && (spanStart === null || s < spanStart)) spanStart = s;
    if (f && (spanFinish === null || f > spanFinish)) spanFinish = f;
  }
  return {
    total: activities.length,
    inProgress,
    completed,
    avgPercent: activities.length ? Math.round(pctSum / activities.length) : 0,
    spanStart,
    spanFinish,
  };
}

/**
 * Flatten `nodes` (preorder) + their activities into visible rows, honouring
 * collapse. Empty bands (no filtered activity anywhere in their subtree) are
 * dropped so a status filter doesn't leave a forest of empty headers.
 */
export function buildGridRows(
  nodes: WbsNode[],
  activitiesByLeaf: Map<string, Activity[]>,
  collapsed: Set<string>,
): GridRow[] {
  // subtree activity list per node (nodes small; O(n·depth) is fine)
  const subtree = new Map<string, Activity[]>();
  for (const n of nodes) subtree.set(n.wbs_id, []);
  for (const n of nodes) {
    const direct = activitiesByLeaf.get(n.wbs_id) ?? [];
    if (direct.length === 0) continue;
    for (const ancestorId of n.path_ids) {
      const bucket = subtree.get(ancestorId);
      if (bucket) bucket.push(...direct);
    }
  }

  const childCount = new Map<string, number>();
  for (const n of nodes) {
    if (!n.parent_wbs_id) continue;
    childCount.set(n.parent_wbs_id, (childCount.get(n.parent_wbs_id) ?? 0) + 1);
  }

  const rows: GridRow[] = [];
  for (const n of nodes) {
    const sub = subtree.get(n.wbs_id) ?? [];
    if (sub.length === 0) continue; // empty band
    const ancestorCollapsed = n.path_ids.slice(0, -1).some((pid) => collapsed.has(pid));
    if (ancestorCollapsed) continue;

    const isCollapsed = collapsed.has(n.wbs_id);
    const stats = rollup(sub);
    rows.push({
      kind: "band",
      key: `band:${n.wbs_id}`,
      node: n,
      label: n.wbs_name,
      outlineCode: n.outline_code,
      depth: n.depth,
      wbsId: n.wbs_id,
      collapsed: isCollapsed,
      hasChildren: (childCount.get(n.wbs_id) ?? 0) > 0 || (activitiesByLeaf.get(n.wbs_id) ?? []).length > 0,
      ...stats,
    });

    if (!isCollapsed) {
      for (const a of activitiesByLeaf.get(n.wbs_id) ?? []) {
        rows.push({ kind: "activity", key: `act:${a.id}`, activity: a, depth: n.depth + 1 });
      }
    }
  }

  // Activities with no resolvable WBS node.
  const ungrouped = activitiesByLeaf.get(UNGROUPED_KEY) ?? [];
  if (ungrouped.length > 0) {
    const collapsedU = collapsed.has(UNGROUPED_KEY);
    rows.push({
      kind: "band",
      key: `band:${UNGROUPED_KEY}`,
      node: null,
      label: "Ungrouped",
      outlineCode: "—",
      depth: 0,
      wbsId: UNGROUPED_KEY,
      collapsed: collapsedU,
      hasChildren: true,
      ...rollup(ungrouped),
    });
    if (!collapsedU) {
      for (const a of ungrouped) {
        rows.push({ kind: "activity", key: `act:${a.id}`, activity: a, depth: 1 });
      }
    }
  }

  return rows;
}
