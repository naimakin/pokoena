import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.activity import Activity
from app.models.project import Project
from app.models.wbs_node import WbsNode
from app.schemas.wbs import WbsNodeOut

router = APIRouter(prefix="/projects/{project_id}/wbs-nodes", tags=["wbs"])


@router.get("", response_model=list[WbsNodeOut])
def list_wbs_nodes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[WbsNodeOut]:
    """The project's WBS tree as a flat, seq_num-ordered list — the frontend
    reassembles the hierarchy from parent_wbs_id. Each node also carries a
    direct and a rolled-up activity count (activities join the tree via
    Activity.wbs_path, which xer_import sets to the activity's TASK.wbs_id)."""
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
        )
        for n in nodes
    ]
