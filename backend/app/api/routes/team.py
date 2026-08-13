import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, require_user_management
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.schemas.password_reset import PasswordResetLinkOut
from app.schemas.team import TeamMemberOut
from app.services import audit
from app.services.password_reset import create_password_reset

router = APIRouter(prefix="/team", tags=["team"])


@router.get("", response_model=list[TeamMemberOut])
def list_team(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_user_management),
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
            title=user.title,
            phone=user.phone,
            role=membership.role,
            project_role=membership.project_role,
            is_active=membership.is_active,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.delete("/{user_tenant_role_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_team_member(
    user_tenant_role_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_user_management),
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


@router.post("/{user_tenant_role_id}/reset-password-link", response_model=PasswordResetLinkOut)
def create_team_member_reset_link(
    user_tenant_role_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_user_management),
) -> PasswordResetLinkOut:
    """Same "no email provider yet, hand the link back directly" pattern as
    the platform admin's tenant-admin reset link. A user_management-role
    employee (not a company_admin) can reset ordinary teammates but not
    another company_admin's password — resetting a peer or superior's
    credentials is a company_admin-only action."""
    membership = db.get(UserTenantRole, user_tenant_role_id)
    if membership is None or membership.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")
    if membership.role == TenantRole.company_admin and ctx.role != TenantRole.company_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only a company admin can reset another admin's password"
        )

    user = db.get(User, membership.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")

    _reset, reset_url = create_password_reset(db, user_id=user.id, created_by_user_id=ctx.user.id)
    audit.log(
        "password_reset.created", tenant_id=ctx.tenant_id, actor_user_id=ctx.user.id,
        target_type="user", target_id=user.id,
    )
    return PasswordResetLinkOut(email=user.email, reset_url=reset_url)
