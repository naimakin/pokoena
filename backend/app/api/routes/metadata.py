"""Small post-import metadata editor — ports the reference project's
`routes_metadata.py` (rename/adjust Calendar, Resource, and Activity Code
display fields after import). Unlike the reference, which mutates an
in-memory snapshot.json, these edits go straight to our live `calendars`/
`resources`/`activity_code_values` rows — there's no separate snapshot to
keep in sync."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.activity_code import ActivityCodeValue
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource import Resource
from app.schemas.metadata import ActivityCodeValuePatch, CalendarOut, CalendarPatch, ResourceOut, ResourcePatch

router = APIRouter(prefix="/projects/{project_id}", tags=["metadata"])


@router.get("/calendars", response_model=list[CalendarOut])
def list_calendars(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> list[Calendar]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    return db.query(Calendar).filter(Calendar.tenant_id == ctx.tenant_id, Calendar.project_id == project_id).all()


@router.patch("/calendars/{calendar_id}", response_model=CalendarOut)
def patch_calendar(
    project_id: uuid.UUID,
    calendar_id: uuid.UUID,
    payload: CalendarPatch,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> Calendar:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)

    calendar = get_tenant_scoped_or_404(db, Calendar, calendar_id, ctx)
    if calendar.project_id != project_id:
        raise HTTPException(status_code=400, detail="Calendar does not belong to this project")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(calendar, field, value)

    db.commit()
    db.refresh(calendar)
    return calendar


@router.get("/resources", response_model=list[ResourceOut])
def list_resources(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> list[Resource]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    return db.query(Resource).filter(Resource.tenant_id == ctx.tenant_id, Resource.project_id == project_id).all()


@router.patch("/resources/{resource_id}", response_model=ResourceOut)
def patch_resource(
    project_id: uuid.UUID,
    resource_id: uuid.UUID,
    payload: ResourcePatch,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> Resource:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)

    resource = get_tenant_scoped_or_404(db, Resource, resource_id, ctx)
    if resource.project_id != project_id:
        raise HTTPException(status_code=400, detail="Resource does not belong to this project")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(resource, field, value)

    db.commit()
    db.refresh(resource)
    return resource


@router.patch("/activity-codes/{code_value_id}")
def patch_activity_code_value(
    project_id: uuid.UUID,
    code_value_id: uuid.UUID,
    payload: ActivityCodeValuePatch,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)

    code_value = get_tenant_scoped_or_404(db, ActivityCodeValue, code_value_id, ctx)
    if code_value.project_id != project_id:
        raise HTTPException(status_code=400, detail="Activity code does not belong to this project")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(code_value, field, value)

    db.commit()
    return {"id": str(code_value_id), "updated": True}
