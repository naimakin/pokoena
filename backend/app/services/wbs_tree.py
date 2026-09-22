"""Builds the WBS page's flattened, depth/outline-annotated tree.

Shared by two sources that both end up as a flat list of "WBS node + activity
counts": the live `wbs_nodes` table (api/routes/wbs.py) and a frozen
`ScheduleImport.wbs_snapshot` for viewing an earlier program (api/routes/
schedule_imports.py). The tree-walk, rollup and outline-coding logic is
identical either way — only where the raw nodes and activity counts came from
differs, which is the caller's job via `WbsNodeLite`.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from app.schemas.wbs import WbsNodeOut


@dataclass
class WbsNodeLite:
    id: uuid.UUID
    wbs_id: str
    parent_wbs_id: str | None
    wbs_short_name: str
    wbs_name: str
    seq_num: int | None


def build_wbs_tree(nodes: list[WbsNodeLite], direct_counts: dict[str, int]) -> list[WbsNodeOut]:
    if not nodes:
        return []

    known_ids = {n.wbs_id for n in nodes}
    children: dict[str | None, list[WbsNodeLite]] = defaultdict(list)
    for n in nodes:
        parent = n.parent_wbs_id if n.parent_wbs_id in known_ids else None
        children[parent].append(n)

    totals: dict[str, int] = {}

    def rollup(node: WbsNodeLite, seen: set[str]) -> int:
        if node.wbs_id in seen:  # defensive: a malformed file could cycle
            return 0
        seen.add(node.wbs_id)
        total = direct_counts.get(node.wbs_id, 0) + sum(rollup(c, seen) for c in children.get(node.wbs_id, []))
        totals[node.wbs_id] = total
        return total

    for root in children.get(None, []):
        rollup(root, set())

    # Preorder walk: assign depth / path_ids / outline_code and produce the
    # return order. `children` lists are already seq_num-ordered (nodes was).
    ordered: list[tuple[WbsNodeLite, int, list[str], str]] = []

    def walk(node: WbsNodeLite, depth: int, ancestors: list[str], parent_code: str, index: int, seen: set[str]) -> None:
        if node.wbs_id in seen:  # defensive: a malformed file could cycle
            return
        seen.add(node.wbs_id)
        # Positional dotted outline ("1", "1.2", "1.2.1") — predictable and P6-like.
        segment = str(index + 1)
        outline_code = f"{parent_code}.{segment}" if parent_code else segment
        path_ids = [*ancestors, node.wbs_id]
        ordered.append((node, depth, path_ids, outline_code))
        for child_index, child in enumerate(children.get(node.wbs_id, [])):
            walk(child, depth + 1, path_ids, outline_code, child_index, seen)

    root_seen: set[str] = set()
    for root_index, root in enumerate(children.get(None, [])):
        walk(root, 0, [], "", root_index, root_seen)

    # Any node not reached from a root (a pure cycle in a malformed file) is
    # still returned, flat, so the list stays complete.
    for leftover_index, n in enumerate(n for n in nodes if n.wbs_id not in root_seen):
        ordered.append((n, 0, [n.wbs_id], str(leftover_index + 1)))

    return [
        WbsNodeOut(
            id=n.id,
            wbs_id=n.wbs_id,
            parent_wbs_id=n.parent_wbs_id,
            wbs_short_name=n.wbs_short_name,
            wbs_name=n.wbs_name,
            seq_num=n.seq_num,
            direct_activity_count=direct_counts.get(n.wbs_id, 0),
            total_activity_count=totals.get(n.wbs_id, direct_counts.get(n.wbs_id, 0)),
            depth=depth,
            path_ids=path_ids,
            outline_code=outline_code,
        )
        for n, depth, path_ids, outline_code in ordered
    ]
