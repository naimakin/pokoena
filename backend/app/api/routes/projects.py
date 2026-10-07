import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    AuthContext,
    get_current_tenant_user,
    get_tenant_scoped_or_404,
    require_project_permission,
    require_role,
)
from app.models.activity import Activity
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import RecoveryPlan
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user_tenant_role import TenantRole
from app.schemas.project import (
    ProjectCreate,
    ProjectOut,
    ProjectScopeCreate,
    ProjectScopeOut,
    ProjectScopeUpdate,
    ProjectUpdate,
    ScopePreviewActivity,
    ScopePreviewIn,
    ScopePreviewOut,
)
from app.services import audit
from app.services.project_deletion import delete_project
from app.services.scope_rules import ScopeRules, apply_scope_rules, scope_activity_counts
from app.services.scope_rules import preview as preview_scope

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


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> Project:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)

    if payload.name is None and payload.code is None:
        raise HTTPException(status_code=422, detail="Nothing to update — send a name and/or a code")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Project name can't be blank")
        project.name = name
    if payload.code is not None:
        code = payload.code.strip()
        if not code:
            raise HTTPException(status_code=400, detail="Project code can't be blank")
        dup = (
            db.query(Project)
            .filter(Project.tenant_id == ctx.tenant_id, Project.code == code, Project.id != project_id)
            .first()
        )
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project code already in use")
        project.code = code

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project(
    project_id: uuid.UUID,
    confirm_code: str,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> None:
    """Permanently deletes the project and every row anywhere in the schema
    that belongs to it — schedule, baselines, progress, risk register,
    recovery plans, saved filters, everything (see services/project_deletion.py
    for the full, deliberately explicit list). There is no undo and no
    export-first step; the frontend's confirmation dialog is expected to make
    that unmistakable. `confirm_code` must match the project's own code
    exactly (like typing a repo name to delete it) — a second, server-side
    guard against deleting the wrong project from a stray or scripted call,
    independent of whatever the UI already confirmed."""
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    if confirm_code != project.code:
        raise HTTPException(status_code=400, detail="Confirmation code doesn't match this project's code")

    name, code = project.name, project.code
    delete_project(db, ctx.tenant_id, project_id)
    db.commit()
    audit.log(
        "project.deleted",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user.id,
        target_type="project",
        target_id=project_id,
        event_metadata={"name": name, "code": code},
    )


def _scope_out(scope: ProjectScope, activity_counts: dict, member_counts: dict) -> ProjectScopeOut:
    out = ProjectScopeOut.model_validate(scope)
    out.wbs_ids = list(scope.wbs_ids or [])
    out.code_value_ids = list(scope.code_value_ids or [])
    out.activity_count = activity_counts.get(scope.id, 0)
    out.member_count = member_counts.get(scope.id, 0)
    return out


def _member_counts(db: Session, ctx: AuthContext, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
    return dict(
        db.query(SubcontractorScopeAssignment.project_scope_id, func.count(SubcontractorScopeAssignment.id))
        .join(ProjectScope, ProjectScope.id == SubcontractorScopeAssignment.project_scope_id)
        .filter(ProjectScope.tenant_id == ctx.tenant_id, ProjectScope.project_id == project_id)
        .group_by(SubcontractorScopeAssignment.project_scope_id)
        .all()
    )


def _clean_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in values if v and v.strip()))


@router.get("/{project_id}/scopes", response_model=list[ProjectScopeOut])
def list_project_scopes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[ProjectScopeOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    query = db.query(ProjectScope).filter(ProjectScope.project_id == project_id)
    if ctx.role == TenantRole.subcontractor:
        if not ctx.scope_ids:
            return []
        query = query.filter(ProjectScope.id.in_(ctx.scope_ids))
    scopes = query.order_by(ProjectScope.name).all()
    activity_counts = scope_activity_counts(db, ctx.tenant_id, project_id)
    member_counts = _member_counts(db, ctx, project_id) if ctx.role != TenantRole.subcontractor else {}
    return [_scope_out(s, activity_counts, member_counts) for s in scopes]


@router.post(
    "/{project_id}/scopes", response_model=ProjectScopeOut, status_code=status.HTTP_201_CREATED
)
def create_project_scope(
    project_id: uuid.UUID,
    payload: ProjectScopeCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> ProjectScopeOut:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    scope = ProjectScope(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project.id,
        subcontractor_org_id=_checked_org(db, ctx, payload.subcontractor_org_id),
        name=payload.name.strip(),
        discipline=payload.discipline.strip(),
        wbs_ids=_clean_ids(payload.wbs_ids),
        code_value_ids=_clean_ids(payload.code_value_ids),
    )
    db.add(scope)
    db.flush()
    counts = apply_scope_rules(db, ctx.tenant_id, project.id)
    db.commit()
    db.refresh(scope)
    audit.log(
        "scope.created", tenant_id=ctx.tenant_id, actor_user_id=ctx.user.id,
        target_type="project_scope", target_id=scope.id, event_metadata={"name": scope.name},
    )
    return _scope_out(scope, counts, {})


def _checked_org(db: Session, ctx: AuthContext, org_id: uuid.UUID | None) -> uuid.UUID | None:
    if org_id is None:
        return None
    org = db.get(SubcontractorOrganization, org_id)
    if org is None or org.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown organization")
    return org_id


def _scope_or_404(db: Session, ctx: AuthContext, project_id: uuid.UUID, scope_id: uuid.UUID) -> ProjectScope:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    scope = get_tenant_scoped_or_404(db, ProjectScope, scope_id, ctx)
    if scope.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ProjectScope not found")
    return scope


@router.patch("/{project_id}/scopes/{scope_id}", response_model=ProjectScopeOut)
def update_project_scope(
    project_id: uuid.UUID,
    scope_id: uuid.UUID,
    payload: ProjectScopeUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> ProjectScopeOut:
    """Rename a scope or change its rule; a rule change re-assigns the
    project's activities straight away."""
    scope = _scope_or_404(db, ctx, project_id, scope_id)
    sent = payload.model_fields_set
    if payload.name is not None:
        scope.name = payload.name.strip()
    if payload.discipline is not None:
        scope.discipline = payload.discipline.strip()
    if "subcontractor_org_id" in sent:
        scope.subcontractor_org_id = _checked_org(db, ctx, payload.subcontractor_org_id)
    if payload.wbs_ids is not None:
        scope.wbs_ids = _clean_ids(payload.wbs_ids)
    if payload.code_value_ids is not None:
        scope.code_value_ids = _clean_ids(payload.code_value_ids)
    db.flush()
    counts = apply_scope_rules(db, ctx.tenant_id, project_id)
    db.commit()
    db.refresh(scope)
    audit.log(
        "scope.updated", tenant_id=ctx.tenant_id, actor_user_id=ctx.user.id,
        target_type="project_scope", target_id=scope.id, event_metadata={"fields": sorted(sent)},
    )
    return _scope_out(scope, counts, _member_counts(db, ctx, project_id))


@router.delete("/{project_id}/scopes/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_scope(
    project_id: uuid.UUID,
    scope_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> None:
    """Deletes the scope and its subcontractor assignments. Its activities go
    back to no scope (or to another scope whose rule matches them); recovery
    plans a subcontractor wrote under it pass to the company."""
    scope = _scope_or_404(db, ctx, project_id, scope_id)
    db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_scope_id == scope.id).update(
        {Activity.project_scope_id: None}, synchronize_session=False
    )
    db.query(RecoveryPlan).filter(
        RecoveryPlan.tenant_id == ctx.tenant_id, RecoveryPlan.project_scope_id == scope.id
    ).update({RecoveryPlan.project_scope_id: None}, synchronize_session=False)
    db.query(SubcontractorScopeAssignment).filter(
        SubcontractorScopeAssignment.tenant_id == ctx.tenant_id,
        SubcontractorScopeAssignment.project_scope_id == scope.id,
    ).delete(synchronize_session=False)
    name = scope.name
    db.delete(scope)
    db.flush()
    apply_scope_rules(db, ctx.tenant_id, project_id)
    db.commit()
    audit.log(
        "scope.deleted", tenant_id=ctx.tenant_id, actor_user_id=ctx.user.id,
        target_type="project_scope", target_id=scope_id, event_metadata={"name": name},
    )


@router.post("/{project_id}/scopes/preview", response_model=ScopePreviewOut)
def preview_project_scope(
    project_id: uuid.UUID,
    payload: ScopePreviewIn,
    scope_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> ScopePreviewOut:
    """What a rule would select, before saving it. `scope_id` is the scope
    being edited, so its own activities don't count as claimed elsewhere."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    rules = ScopeRules(frozenset(_clean_ids(payload.wbs_ids)), frozenset(_clean_ids(payload.code_value_ids)))
    hits = preview_scope(db, ctx.tenant_id, project_id, rules)
    hits.sort(key=lambda a: a.external_id)
    claimed = sum(1 for a in hits if a.project_scope_id is not None and a.project_scope_id != scope_id)
    return ScopePreviewOut(
        count=len(hits),
        claimed_elsewhere=claimed,
        sample=[ScopePreviewActivity(external_id=a.external_id, name=a.name, wbs_path=a.wbs_path) for a in hits[:12]],
    )
