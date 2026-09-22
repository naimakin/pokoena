import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.activity import Activity
from app.models.project import Project
from app.models.wbs_node import WbsNode
from app.schemas.wbs import WbsNodeCreate, WbsNodeOut
from app.services.wbs_tree import WbsNodeLite, build_wbs_tree

router = APIRouter(prefix="/projects/{project_id}/wbs-nodes", tags=["wbs"])


@router.get("", response_model=list[WbsNodeOut])
def list_wbs_nodes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[WbsNodeOut]:
    """The project's LIVE WBS tree (i.e. the current update's — see
    services/xer_import.py, which wholesale-replaces this table on every
    import) as a preorder-flattened list carrying depth, path_ids and a dotted
    outline_code — the frontend renders it as an indented register and
    reassembles the hierarchy from parent_wbs_id. Each node also carries a
    direct and a rolled-up activity count (activities join the tree via
    Activity.wbs_path, which xer_import sets to the activity's TASK.wbs_id).
    To view an earlier program's WBS, see GET .../schedule-imports/{id}/wbs-nodes."""
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

    lite = [
        WbsNodeLite(
            id=n.id, wbs_id=n.wbs_id, parent_wbs_id=n.parent_wbs_id,
            wbs_short_name=n.wbs_short_name, wbs_name=n.wbs_name, seq_num=n.seq_num,
        )
        for n in nodes
    ]
    return build_wbs_tree(lite, direct)


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
