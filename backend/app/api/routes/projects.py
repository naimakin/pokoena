import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    AuthContext,
    get_current_tenant_user,
    get_tenant_scoped_or_404,
    require_project_permission,
    require_role,
)
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.user_tenant_role import TenantRole
from app.schemas.project import ProjectCreate, ProjectOut, ProjectScopeCreate, ProjectScopeOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> list[Project]:
    query = db.query(Project).filter(Project.tenant_id == ctx.tenant_id)
    if ctx.role == TenantRole.company_employee:
        # Employees only see projects they've been explicitly given a
        # ProjectMembership on — company admins see the whole tenant.
        query = query.join(
            ProjectMembership, ProjectMembership.project_id == Project.id
        ).filter(ProjectMembership.user_id == ctx.user.id)
    elif ctx.role == TenantRole.subcontractor:
        # "Not other projects, not company-wide data" — a subcontractor only
        # ever sees projects that contain at least one scope they're assigned to.
        if not ctx.scope_ids:
            return []
        query = (
            query.join(ProjectScope, ProjectScope.project_id == Project.id)
            .filter(ProjectScope.id.in_(ctx.scope_ids))
            .distinct()
        )
    return query.order_by(Project.name).all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> Project:
    exists = (
        db.query(Project)
        .filter(Project.tenant_id == ctx.tenant_id, Project.code == payload.code)
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project code already in use")

    project = Project(id=uuid.uuid4(), tenant_id=ctx.tenant_id, name=payload.name, code=payload.code)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> Project:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    return project


@router.get("/{project_id}/scopes", response_model=list[ProjectScopeOut])
def list_project_scopes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[ProjectScope]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    query = db.query(ProjectScope).filter(ProjectScope.project_id == project_id)
    if ctx.role == TenantRole.subcontractor:
        if not ctx.scope_ids:
            return []
        query = query.filter(ProjectScope.id.in_(ctx.scope_ids))
    return query.order_by(ProjectScope.name).all()


@router.post(
    "/{project_id}/scopes", response_model=ProjectScopeOut, status_code=status.HTTP_201_CREATED
)
def create_project_scope(
    project_id: uuid.UUID,
    payload: ProjectScopeCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> ProjectScope:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    scope = ProjectScope(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project.id,
        subcontractor_org_id=payload.subcontractor_org_id,
        name=payload.name,
        discipline=payload.discipline,
    )
    db.add(scope)
    db.commit()
    db.refresh(scope)
    return scope
