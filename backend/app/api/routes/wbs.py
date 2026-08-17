import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.project import Project
from app.models.wbs_node import WbsNode
from app.schemas.wbs import WbsNodeOut

router = APIRouter(prefix="/projects/{project_id}/wbs-nodes", tags=["wbs"])


@router.get("", response_model=list[WbsNodeOut])
def list_wbs_nodes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[WbsNode]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    return (
        db.query(WbsNode)
        .filter(WbsNode.tenant_id == ctx.tenant_id, WbsNode.project_id == project_id)
        .order_by(WbsNode.seq_num)
        .all()
    )
