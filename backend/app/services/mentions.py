"""@mentions in activity comments.

A comment body carries a mention as a token `@[Full Name](user:<uuid>)`: the
name keeps the text readable on its own, the id is what counts. The server is
the source of truth — every id is checked against who may be mentioned on that
activity, and anything else stays plain text (never an error: a stale or
pasted token shouldn't stop someone from commenting).

Who may be mentioned on an activity = who can see it:
- active company admins;
- active company employees who are members of the project and can open
  Delivery (view_delivery — the Activity Ledger and My Desk), so a Dashboard
  Viewer isn't pinged about work they can't open;
- subcontractors assigned to the activity's own scope.
The list never carries emails: anyone on the project can read it.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.deps import AuthContext
from app.models.activity import Activity
from app.models.activity_event import ActivityEvent
from app.models.mention import Mention
from app.models.project_membership import ProjectMembership
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user import User
from app.models.user_tenant_role import (
    PROJECT_ROLE_LABELS,
    Capability,
    TenantRole,
    UserTenantRole,
    capabilities_for,
    parse_project_roles,
)

TOKEN_RE = re.compile(r"@\[([^\]\n]{1,120})\]\(user:([0-9a-fA-F-]{36})\)")
MAX_MENTIONS_PER_COMMENT = 10


@dataclass(frozen=True)
class Mentionable:
    user_id: uuid.UUID
    full_name: str
    label: str


def mentionable_users(db: Session, ctx: AuthContext, activity: Activity) -> list[Mentionable]:
    rows = (
        db.query(UserTenantRole, User)
        .join(User, User.id == UserTenantRole.user_id)
        .filter(
            UserTenantRole.tenant_id == ctx.tenant_id,
            UserTenantRole.is_active.is_(True),
            User.is_active.is_(True),
        )
        .all()
    )
    members = {
        uid
        for (uid,) in db.query(ProjectMembership.user_id).filter(
            ProjectMembership.tenant_id == ctx.tenant_id, ProjectMembership.project_id == activity.project_id
        )
    }
    scope_users: set[uuid.UUID] = set()
    if activity.project_scope_id is not None:
        scope_users = {
            uid
            for (uid,) in db.query(SubcontractorScopeAssignment.user_id).filter(
                SubcontractorScopeAssignment.tenant_id == ctx.tenant_id,
                SubcontractorScopeAssignment.project_scope_id == activity.project_scope_id,
            )
        }
    org_names = dict(
        db.query(SubcontractorOrganization.id, SubcontractorOrganization.name).filter(
            SubcontractorOrganization.tenant_id == ctx.tenant_id
        )
    )

    out: list[Mentionable] = []
    for membership, user in rows:
        roles = parse_project_roles(membership.project_roles, membership.role)
        if membership.role == TenantRole.company_admin:
            label = "Company admin"
        elif membership.role == TenantRole.company_employee:
            if user.id not in members or Capability.view_delivery not in capabilities_for(membership.role, roles):
                continue
            label = ", ".join(PROJECT_ROLE_LABELS[r] for r in roles if r != r.user_management) or "Employee"
        else:
            if user.id not in scope_users:
                continue
            org = org_names.get(membership.subcontractor_org_id) if membership.subcontractor_org_id else None
            label = f"Subcontractor · {org}" if org else "Subcontractor"
        out.append(Mentionable(user_id=user.id, full_name=user.full_name, label=label))
    out.sort(key=lambda m: m.full_name.lower())
    return out


def mentioned_ids(body: str) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for _name, raw in TOKEN_RE.findall(body or ""):
        try:
            uid = uuid.UUID(raw)
        except ValueError:
            continue
        if uid not in ids:
            ids.append(uid)
    return ids[:MAX_MENTIONS_PER_COMMENT]


def record_mentions(db: Session, ctx: AuthContext, activity: Activity, event: ActivityEvent) -> list[uuid.UUID]:
    """Store a Mention for each valid person tagged in `event` (not the author).
    Flushes; the caller commits with the comment."""
    wanted = [uid for uid in mentioned_ids(event.body or "") if uid != ctx.user.id]
    if not wanted:
        return []
    allowed = {m.user_id for m in mentionable_users(db, ctx, activity)}
    saved = [uid for uid in wanted if uid in allowed]
    for uid in saved:
        db.add(
            Mention(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                project_id=activity.project_id,
                activity_id=activity.id,
                activity_external_id=activity.external_id,
                activity_event_id=event.id,
                mentioned_user_id=uid,
                author_user_id=ctx.user.id,
            )
        )
    db.flush()
    return saved


def plain_text(body: str) -> str:
    """`@[Ana Demir](user:…)` -> `@Ana Demir`, for snippets."""
    return TOKEN_RE.sub(lambda m: f"@{m.group(1)}", body or "")
