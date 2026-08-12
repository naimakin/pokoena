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
    project_role: ProjectRole | None = None,
) -> UserTenantRole:
    membership = UserTenantRole(
        id=uuid.uuid4(),
        user_id=user.id,
        tenant_id=tenant.id,
        role=role,
        project_role=project_role,
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
