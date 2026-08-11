import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, require_role
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.schemas.team import TeamMemberOut
from app.services import audit

router = APIRouter(prefix="/team", tags=["team"])


@router.get("", response_model=list[TeamMemberOut])
def list_team(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin, TenantRole.company_employee)),
) -> list[TeamMemberOut]:
    rows = (
        db.query(UserTenantRole, User)
        .join(User, User.id == UserTenantRole.user_id)
        .filter(UserTenantRole.tenant_id == ctx.tenant_id)
        .order_by(UserTenantRole.created_at.asc())
        .all()
    )
    return [
        TeamMemberOut(
            user_tenant_role_id=membership.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            is_active=membership.is_active,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.delete("/{user_tenant_role_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_team_member(
    user_tenant_role_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> None:
    """Soft-revokes tenant access (is_active=False) rather than deleting the
    row — audit history and any prior activity attributed to this person stays
    intact."""
    membership = db.get(UserTenantRole, user_tenant_role_id)
    if membership is None or membership.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")
    if membership.user_id == ctx.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can't remove your own access")

    membership.is_active = False
    db.commit()
    audit.log(
        "role.revoked",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user.id,
        target_type="user_tenant_role",
        target_id=membership.id,
        event_metadata={"removed_user_id": str(membership.user_id)},
    )
