import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, require_user_management
from app.models.subcontractor_organization import SubcontractorOrganization
from app.schemas.subcontractor_organization import SubcontractorOrgCreate, SubcontractorOrgOut

router = APIRouter(prefix="/subcontractor-organizations", tags=["subcontractor-organizations"])


@router.get("", response_model=list[SubcontractorOrgOut])
def list_subcontractor_organizations(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[SubcontractorOrganization]:
    return (
        db.query(SubcontractorOrganization)
        .filter(SubcontractorOrganization.tenant_id == ctx.tenant_id)
        .order_by(SubcontractorOrganization.name)
        .all()
    )


@router.post("", response_model=SubcontractorOrgOut, status_code=201)
def create_subcontractor_organization(
    payload: SubcontractorOrgCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_user_management),
) -> SubcontractorOrganization:
    org = SubcontractorOrganization(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        name=payload.name,
        discipline=payload.discipline,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org
