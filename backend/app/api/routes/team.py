import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, require_user_management
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole, parse_project_roles
from app.schemas.password_reset import PasswordResetLinkOut
from app.schemas.team import TeamMemberOut, TeamMemberUpdate
from app.services import audit
from app.services.email_change import belongs_to_another_tenant, check_email_change
from app.services.team_roles import check_project_roles
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
    return [_member_out(db, ctx, membership, user) for membership, user in rows]


def _member_out(db: Session, ctx: AuthContext, membership: UserTenantRole, user: User) -> TeamMemberOut:
    project_ids: list[uuid.UUID] = []
    scope_ids: list[uuid.UUID] = []
    if membership.role == TenantRole.company_employee:
        project_ids = [
            pid
            for (pid,) in db.query(ProjectMembership.project_id).filter(
                ProjectMembership.tenant_id == ctx.tenant_id, ProjectMembership.user_id == user.id
            )
        ]
    elif membership.role == TenantRole.subcontractor:
        scope_ids = [
            sid
            for (sid,) in db.query(SubcontractorScopeAssignment.project_scope_id).filter(
                SubcontractorScopeAssignment.tenant_id == ctx.tenant_id,
                SubcontractorScopeAssignment.user_id == user.id,
            )
        ]
    org = db.get(SubcontractorOrganization, membership.subcontractor_org_id) if membership.subcontractor_org_id else None
    return TeamMemberOut(
        user_tenant_role_id=membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        title=user.title,
        phone=user.phone,
        role=membership.role,
        project_roles=parse_project_roles(membership.project_roles, membership.role),
        is_active=membership.is_active,
        created_at=membership.created_at,
        project_ids=project_ids,
        scope_ids=scope_ids,
        subcontractor_org_id=membership.subcontractor_org_id,
        subcontractor_org_name=org.name if org else None,
    )


def _sync_rows(db: Session, current: dict, wanted: set, make) -> None:
    """Make the set of link rows (keyed by the id they point at) equal `wanted`."""
    for key, row in current.items():
        if key not in wanted:
            db.delete(row)
    for key in wanted - current.keys():
        db.add(make(key))


@router.patch("/{user_tenant_role_id}", response_model=TeamMemberOut)
def update_team_member(
    user_tenant_role_id: uuid.UUID,
    payload: TeamMemberUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_user_management),
) -> TeamMemberOut:
    """Edit a member: details, project roles, and what they can reach -
    projects for an employee, scopes (and firm) for a subcontractor. Only the
    fields sent change. A subcontractor's new scopes reach their session on its
    next refresh (access tokens live 15 minutes, see deps.require_scope_access)."""
    membership = db.get(UserTenantRole, user_tenant_role_id)
    if membership is None or membership.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")
    user = db.get(User, membership.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")

    sent = payload.model_fields_set
    access_fields = {"project_roles", "project_ids", "scope_ids", "subcontractor_org_id", "is_active"}
    if membership.role == TenantRole.company_admin:
        if ctx.role != TenantRole.company_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a company admin can edit an admin")
        if sent & access_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="A company admin already has access to every project"
            )
    if membership.user_id == ctx.user.id and sent & access_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't change your own access")
    is_sub = membership.role == TenantRole.subcontractor
    if is_sub and "project_ids" in sent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A subcontractor reaches projects through their scopes"
        )
    if not is_sub and sent & {"scope_ids", "subcontractor_org_id"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only subcontractors have scopes")

    changed: list[str] = []
    old_email = user.email
    if "email" in sent and payload.email and payload.email.strip().lower() != user.email:
        if ctx.role != TenantRole.company_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a company admin can change an email")
        user.email = check_email_change(user, ctx.tenant_id, payload.email)
        changed.append("email")
    if "full_name" in sent and payload.full_name and payload.full_name.strip():
        user.full_name = payload.full_name.strip()
        changed.append("full_name")
    if "title" in sent:
        user.title = (payload.title or "").strip() or None
        changed.append("title")
    if "phone" in sent:
        user.phone = (payload.phone or "").strip() or None
        changed.append("phone")

    if "project_roles" in sent:
        roles = check_project_roles(membership.role, payload.project_roles or [], ctx)
        membership.project_roles = [r.value for r in roles]
        changed.append("project_roles")

    if "project_ids" in sent:
        wanted = set(payload.project_ids or [])
        known = {pid for (pid,) in db.query(Project.id).filter(Project.tenant_id == ctx.tenant_id, Project.id.in_(wanted))}
        if wanted - known:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown project")
        current = {
            m.project_id: m
            for m in db.query(ProjectMembership).filter(
                ProjectMembership.tenant_id == ctx.tenant_id, ProjectMembership.user_id == user.id
            )
        }
        _sync_rows(
            db, current, wanted,
            lambda pid: ProjectMembership(id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=pid, user_id=user.id),
        )
        changed.append("project_ids")

    if "scope_ids" in sent:
        wanted = set(payload.scope_ids or [])
        known = {
            sid
            for (sid,) in db.query(ProjectScope.id).filter(
                ProjectScope.tenant_id == ctx.tenant_id, ProjectScope.id.in_(wanted)
            )
        }
        if wanted - known:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown scope")
        current = {
            a.project_scope_id: a
            for a in db.query(SubcontractorScopeAssignment).filter(
                SubcontractorScopeAssignment.tenant_id == ctx.tenant_id,
                SubcontractorScopeAssignment.user_id == user.id,
            )
        }
        _sync_rows(
            db, current, wanted,
            lambda sid: SubcontractorScopeAssignment(
                id=uuid.uuid4(), tenant_id=ctx.tenant_id, user_id=user.id,
                project_scope_id=sid, assigned_by_user_id=ctx.user.id,
            ),
        )
        changed.append("scope_ids")

    if "subcontractor_org_id" in sent:
        org_id = payload.subcontractor_org_id
        if org_id is not None:
            org = db.get(SubcontractorOrganization, org_id)
            if org is None or org.tenant_id != ctx.tenant_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown organization")
        membership.subcontractor_org_id = org_id
        changed.append("subcontractor_org_id")

    if payload.is_active:
        membership.is_active = True
        changed.append("is_active")

    db.commit()
    if "email" in changed:
        audit.log(
            "user.email_changed",
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user.id,
            target_type="user",
            target_id=user.id,
            event_metadata={"old_email": old_email, "new_email": user.email},
        )
    audit.log(
        "role.updated",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user.id,
        target_type="user_tenant_role",
        target_id=membership.id,
        event_metadata={"user_id": str(user.id), "fields": changed},
    )
    db.refresh(membership)
    db.refresh(user)
    return _member_out(db, ctx, membership, user)


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
    if membership.role == TenantRole.company_admin and ctx.role != TenantRole.company_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a company admin can remove an admin")

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
    if user.is_platform_admin or belongs_to_another_tenant(user.id, ctx.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This person also uses their account at another company, so it can't be reset from here",
        )

    _reset, reset_url = create_password_reset(db, user_id=user.id, created_by_user_id=ctx.user.id)
    audit.log(
        "password_reset.created", tenant_id=ctx.tenant_id, actor_user_id=ctx.user.id,
        target_type="user", target_id=user.id,
    )
    return PasswordResetLinkOut(email=user.email, reset_url=reset_url)
