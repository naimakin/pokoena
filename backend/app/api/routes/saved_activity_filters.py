import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_tenant_scoped_or_404, require_role
from app.models.project import Project
from app.models.saved_activity_filter import SavedActivityFilter
from app.models.user_tenant_role import TenantRole
from app.schemas.saved_activity_filter import SavedFilterCreate, SavedFilterOut, SavedFilterUpdate

router = APIRouter(prefix="/projects/{project_id}/saved-filters", tags=["saved-filters"])

_ROLE = require_role(TenantRole.company_admin, TenantRole.company_employee)


def _to_out(row: SavedActivityFilter, ctx: AuthContext) -> SavedFilterOut:
    out = SavedFilterOut.model_validate(row)
    out.is_owner = row.user_id == ctx.user.id
    return out


@router.get("", response_model=list[SavedFilterOut])
def list_saved_filters(
    project_id: uuid.UUID,
    view: str = Query(default="progress", max_length=40),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> list[SavedFilterOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    rows = (
        db.query(SavedActivityFilter)
        .filter(
            SavedActivityFilter.tenant_id == ctx.tenant_id,
            SavedActivityFilter.project_id == project_id,
            SavedActivityFilter.view_key == view,
            (SavedActivityFilter.user_id == ctx.user.id) | SavedActivityFilter.is_shared.is_(True),
        )
        .order_by(SavedActivityFilter.name)
        .all()
    )
    return [_to_out(r, ctx) for r in rows]


@router.post("", response_model=SavedFilterOut, status_code=201)
def create_saved_filter(
    project_id: uuid.UUID,
    payload: SavedFilterCreate,
    view: str = Query(default="progress", max_length=40),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> SavedFilterOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    row = SavedActivityFilter(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        user_id=ctx.user.id,
        view_key=view,
        name=payload.name,
        criteria=payload.criteria,
        is_shared=payload.is_shared,
        filter_version=payload.filter_version,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A filter with that name already exists")
    db.refresh(row)
    return _to_out(row, ctx)


def _get_owned(db: Session, project_id: uuid.UUID, filter_id: uuid.UUID, ctx: AuthContext) -> SavedActivityFilter:
    row = get_tenant_scoped_or_404(db, SavedActivityFilter, filter_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="Not found")
    if row.user_id != ctx.user.id:
        raise HTTPException(status_code=403, detail="Not the owner of this filter")
    return row


@router.put("/{filter_id}", response_model=SavedFilterOut)
def update_saved_filter(
    project_id: uuid.UUID,
    filter_id: uuid.UUID,
    payload: SavedFilterUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> SavedFilterOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    row = _get_owned(db, project_id, filter_id, ctx)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is not None:
            setattr(row, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A filter with that name already exists")
    db.refresh(row)
    return _to_out(row, ctx)


@router.delete("/{filter_id}", status_code=204)
def delete_saved_filter(
    project_id: uuid.UUID,
    filter_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> None:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    row = _get_owned(db, project_id, filter_id, ctx)
    db.delete(row)
    db.commit()
