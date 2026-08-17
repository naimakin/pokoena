import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.activity_code import ActivityCodeType, ActivityCodeValue
from app.models.project import Project
from app.schemas.activity_code import ActivityCodesOut

router = APIRouter(prefix="/projects/{project_id}/activity-codes", tags=["activity-codes"])


@router.get("", response_model=ActivityCodesOut)
def get_activity_codes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ActivityCodesOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    code_types = (
        db.query(ActivityCodeType)
        .filter(ActivityCodeType.tenant_id == ctx.tenant_id, ActivityCodeType.project_id == project_id)
        .all()
    )
    code_values = (
        db.query(ActivityCodeValue)
        .filter(ActivityCodeValue.tenant_id == ctx.tenant_id, ActivityCodeValue.project_id == project_id)
        .order_by(ActivityCodeValue.seq_num)
        .all()
    )

    return ActivityCodesOut(code_types=code_types, code_values=code_values)
