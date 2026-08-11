from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.deps import AuthContext, require_role
from app.models.invite import Invite
from app.models.tenant import Tenant
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.schemas.invite import InviteAccept, InviteCreate, InviteOut, InvitePreview
from app.schemas.user import UserOut
from app.services import audit
from app.services.invites import InviteError, accept_invite, create_invite, get_invite_preview
from app.services.tenant_session import issue_tenant_session

router = APIRouter(tags=["invites"])


@router.post(
    "/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED
)
def create_tenant_invite(
    payload: InviteCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> Invite:
    invite_payload: dict = {}
    if payload.role == TenantRole.subcontractor:
        invite_payload["project_scope_ids"] = [str(s) for s in payload.project_scope_ids]
        if payload.subcontractor_org_id:
            invite_payload["subcontractor_org_id"] = str(payload.subcontractor_org_id)
    elif payload.role == TenantRole.company_employee:
        invite_payload["project_memberships"] = [
            {"project_id": str(m.project_id), "permission": m.permission.value}
            for m in payload.project_memberships
        ]
    elif payload.role == TenantRole.company_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Additional company admins aren't invited through this endpoint yet",
        )

    tenant = db.get(Tenant, ctx.tenant_id)
    invite = create_invite(
        db=db,
        tenant_id=ctx.tenant_id,
        email=payload.email,
        role=payload.role,
        invited_by_user_id=ctx.user.id,
        tenant_name=tenant.name if tenant else None,
        payload=invite_payload,
    )
    audit.log(
        "invite.created",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user.id,
        target_type="invite",
        target_id=invite.id,
        event_metadata={"email": invite.email, "role": invite.role.value},
    )
    return invite


@router.get("/invites", response_model=list[InviteOut])
def list_tenant_invites(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> list[Invite]:
    return (
        db.query(Invite)
        .filter(Invite.tenant_id == ctx.tenant_id)
        .order_by(Invite.created_at.desc())
        .all()
    )


@router.get("/invites/{token}", response_model=InvitePreview)
def preview_invite(token: str, db: Session = Depends(get_db)) -> InvitePreview:
    try:
        invite = get_invite_preview(db, token)
    except InviteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    tenant = db.get(Tenant, invite.tenant_id)
    return InvitePreview(
        email=invite.email,
        role=invite.role,
        tenant_name=tenant.name if tenant else "",
        expires_at=invite.expires_at,
    )


@router.post(
    "/invites/{token}/accept",
    response_model=UserOut,
    dependencies=[Depends(rate_limit("invite_accept", limit=10, window_seconds=60))],
)
def accept_tenant_invite(
    token: str, payload: InviteAccept, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    try:
        user, invite = accept_invite(
            db, raw_token=token, password=payload.password, full_name=payload.full_name
        )
    except InviteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    membership = (
        db.query(UserTenantRole)
        .filter(UserTenantRole.user_id == user.id, UserTenantRole.tenant_id == invite.tenant_id)
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invite acceptance failed"
        )

    audit.log(
        "invite.accepted",
        tenant_id=membership.tenant_id,
        actor_user_id=user.id,
        target_type="invite",
        target_id=invite.id,
    )
    return issue_tenant_session(response, db, user, membership)
