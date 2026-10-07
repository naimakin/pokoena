"""Small test-only helpers for building the tenant/user graph most tests need.
Not a general ORM abstraction — just enough to keep individual tests readable."""

import uuid

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.project import Project
from app.models.project_scope import ProjectScope
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.models.user_tenant_role import ProjectRole, TenantRole, UserTenantRole


def create_tenant(db: Session, name: str = "Acme GC", slug: str | None = None) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        name=name,
        slug=slug or f"tenant-{uuid.uuid4().hex[:8]}",
        status=TenantStatus.active,
    )
    db.add(tenant)
    db.commit()
    return tenant


def create_user(
    db: Session,
    email: str,
    password: str = "secret123",
    full_name: str = "Test User",
    is_platform_admin: bool = False,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_platform_admin=is_platform_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def add_membership(
    db: Session,
    user: User,
    tenant: Tenant,
    role: TenantRole,
    subcontractor_org_id: uuid.UUID | None = None,
    project_roles: list[ProjectRole] | None = None,
) -> UserTenantRole:
    if project_roles is None and role == TenantRole.subcontractor:
        # What the invite form gives a subcontractor by default.
        project_roles = [ProjectRole.activity_status_updater]
    membership = UserTenantRole(
        id=uuid.uuid4(),
        user_id=user.id,
        tenant_id=tenant.id,
        role=role,
        project_roles=[r.value for r in (project_roles or [])],
        subcontractor_org_id=subcontractor_org_id,
        is_active=True,
    )
    db.add(membership)
    db.commit()
    return membership


def create_project(db: Session, tenant: Tenant, name: str = "Test Project", code: str | None = None) -> Project:
    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name=name, code=code or f"P-{uuid.uuid4().hex[:6]}"
    )
    db.add(project)
    db.commit()
    return project


def create_project_scope(
    db: Session, tenant: Tenant, project: Project, name: str = "Scope", discipline: str = "General"
) -> ProjectScope:
    scope = ProjectScope(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, name=name, discipline=discipline
    )
    db.add(scope)
    db.commit()
    return scope


def create_activity(db: Session, tenant: Tenant, project: Project, external_id: str, **kw):
    from datetime import date

    from app.models.activity import Activity, ActivityStatus

    row = Activity(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        external_id=external_id,
        name=kw.pop("name", f"Activity {external_id}"),
        discipline=kw.pop("discipline", "General"),
        status=kw.pop("status", ActivityStatus.not_started),
        percent_complete=kw.pop("percent_complete", 0),
        remaining_duration_days=kw.pop("remaining_duration_days", 5),
        planned_finish=kw.pop("planned_finish", date(2026, 6, 1)),
        **kw,
    )
    db.add(row)
    db.commit()
    return row


def create_schedule_import(
    db: Session, tenant: Tenant, project: Project, user, *, revision_no=None, revision_label=None, snapshot=None
):
    from datetime import datetime, timezone

    from app.models.schedule_import import ScheduleImport

    row = ScheduleImport(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        filename=f"{revision_label or 'baseline'}.xer",
        imported_by_user_id=user.id,
        imported_at=datetime.now(timezone.utc),
        revision_no=revision_no,
        revision_label=revision_label,
        activities_snapshot=snapshot or [],
    )
    db.add(row)
    db.commit()
    return row


def create_risk_item(db: Session, tenant: Tenant, project: Project, user, *, code="R-1", **kw):
    from app.models.risk_item import RiskItem, RiskStatus

    p = kw.pop("probability", 3)
    i = kw.pop("impact", 3)
    row = RiskItem(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        code=code,
        title=kw.pop("title", "Steel delivery delay"),
        probability=p,
        impact=i,
        score=p * i,
        status=kw.pop("status", RiskStatus.open),
        created_by_user_id=user.id,
        **kw,
    )
    db.add(row)
    db.commit()
    return row


def create_update_period(db: Session, tenant: Tenant, project: Project, *, number=1, status_open=True):
    from datetime import datetime, timedelta, timezone

    from app.models.update_period import UpdatePeriod, UpdatePeriodStatus

    now = datetime.now(timezone.utc)
    row = UpdatePeriod(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        period_number=number,
        label=f"UPD-{number}",
        opens_at=now,
        deadline_at=now + timedelta(days=7),
        status=UpdatePeriodStatus.open if status_open else UpdatePeriodStatus.closed,
    )
    db.add(row)
    db.commit()
    return row
