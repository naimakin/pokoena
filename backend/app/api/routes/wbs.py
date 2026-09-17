import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.activity import Activity
from app.models.project import Project
from app.models.wbs_node import WbsNode
from app.schemas.wbs import WbsNodeCreate, WbsNodeOut

router = APIRouter(prefix="/projects/{project_id}/wbs-nodes", tags=["wbs"])


@router.get("", response_model=list[WbsNodeOut])
def list_wbs_nodes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[WbsNodeOut]:
    """The project's WBS tree as a preorder-flattened list carrying depth,
    path_ids and a dotted outline_code — the frontend renders it as an indented
    register and reassembles the hierarchy from parent_wbs_id. Each node also
    carries a direct and a rolled-up activity count (activities join the tree
    via Activity.wbs_path, which xer_import sets to the activity's TASK.wbs_id)."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    nodes = (
        db.query(WbsNode)
        .filter(WbsNode.tenant_id == ctx.tenant_id, WbsNode.project_id == project_id)
        .order_by(WbsNode.seq_num)
        .all()
    )
    if not nodes:
        return []

    direct: dict[str, int] = {
        wbs_id: count
        for wbs_id, count in (
            db.query(Activity.wbs_path, func.count(Activity.id))
            .filter(
                Activity.tenant_id == ctx.tenant_id,
                Activity.project_id == project_id,
                Activity.wbs_path.isnot(None),
            )
            .group_by(Activity.wbs_path)
            .all()
        )
    }

    known_ids = {n.wbs_id for n in nodes}
    children: dict[str | None, list[WbsNode]] = defaultdict(list)
    for n in nodes:
        parent = n.parent_wbs_id if n.parent_wbs_id in known_ids else None
        children[parent].append(n)

    totals: dict[str, int] = {}

    def rollup(node: WbsNode, seen: set[str]) -> int:
        if node.wbs_id in seen:  # defensive: a malformed file could cycle
            return 0
        seen.add(node.wbs_id)
        total = direct.get(node.wbs_id, 0) + sum(rollup(c, seen) for c in children.get(node.wbs_id, []))
        totals[node.wbs_id] = total
        return total

    for root in children.get(None, []):
        rollup(root, set())

    # Preorder walk: assign depth / path_ids / outline_code and produce the
    # return order. `children` lists are already seq_num-ordered (nodes was).
    ordered: list[tuple[WbsNode, int, list[str], str]] = []

    def walk(node: WbsNode, depth: int, ancestors: list[str], parent_code: str, index: int, seen: set[str]) -> None:
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
            direct_activity_count=direct.get(n.wbs_id, 0),
            total_activity_count=totals.get(n.wbs_id, direct.get(n.wbs_id, 0)),
            depth=depth,
            path_ids=path_ids,
            outline_code=outline_code,
        )
        for n, depth, path_ids, outline_code in ordered
    ]


@router.post("", response_model=WbsNodeOut, status_code=201)
def create_wbs_node(
    project_id: uuid.UUID,
    payload: WbsNodeCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> WbsNodeOut:
    """Manually adds a WBS node (as opposed to one carried in on a P6 .xer
    import). Given a synthetic wbs_id so it round-trips through XER export
    like any other node. Callers should reload the full tree afterward for
    correct depth/path_ids/outline_code — this response doesn't try to
    recompute those position-derived fields for a single node."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)

    if payload.parent_wbs_id is not None:
        parent = (
            db.query(WbsNode)
            .filter(
                WbsNode.tenant_id == ctx.tenant_id,
                WbsNode.project_id == project_id,
                WbsNode.wbs_id == payload.parent_wbs_id,
            )
            .first()
        )
        if parent is None:
            raise HTTPException(status_code=400, detail="Parent WBS node not found")

    max_seq = (
        db.query(func.max(WbsNode.seq_num))
        .filter(WbsNode.tenant_id == ctx.tenant_id, WbsNode.project_id == project_id)
        .scalar()
    )
    node = WbsNode(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        wbs_id=f"manual-{uuid.uuid4().hex[:12]}",
        parent_wbs_id=payload.parent_wbs_id,
        wbs_short_name=payload.wbs_short_name,
        wbs_name=payload.wbs_name,
        seq_num=(max_seq or 0) + 10,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return WbsNodeOut(
        id=node.id,
        wbs_id=node.wbs_id,
        parent_wbs_id=node.parent_wbs_id,
        wbs_short_name=node.wbs_short_name,
        wbs_name=node.wbs_name,
        seq_num=node.seq_num,
        direct_activity_count=0,
        total_activity_count=0,
    )


@router.delete("/{node_id}", status_code=204)
def delete_wbs_node(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> None:
    node = get_tenant_scoped_or_404(db, WbsNode, node_id, ctx)
    if node.project_id != project_id:
        raise HTTPException(status_code=404, detail="WbsNode not found")
    require_project_permission(db, project_id, ctx, need_edit=True)

    has_children = (
        db.query(WbsNode.id)
        .filter(
            WbsNode.tenant_id == ctx.tenant_id,
            WbsNode.project_id == project_id,
            WbsNode.parent_wbs_id == node.wbs_id,
        )
        .first()
        is not None
    )
    if has_children:
        raise HTTPException(status_code=409, detail="Delete or move this node's children first")

    has_activities = (
        db.query(Activity.id)
        .filter(
            Activity.tenant_id == ctx.tenant_id,
            Activity.project_id == project_id,
            Activity.wbs_path == node.wbs_id,
        )
        .first()
        is not None
    )
    if has_activities:
        raise HTTPException(status_code=409, detail="This WBS node still has activities assigned to it")

    db.delete(node)
    db.commit()
