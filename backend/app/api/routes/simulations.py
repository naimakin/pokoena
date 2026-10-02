"""Schedule Simulation (Planning): what-if runs on a copy of the current
programme, and saved scenarios. Runs are read-only — nothing here writes to the
live schedule (services/schedule_simulation.py). Company-side, like QSRA:
subcontractors are excluded; anyone who can view the project can run and see
scenarios, saving needs an edit-capable role, and renaming / deleting a
scenario is for whoever saved it (or a company admin)."""

import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.project import Project
from app.models.schedule_simulation import ScheduleSimulation
from app.models.user import User
from app.models.user_tenant_role import TenantRole
from app.services import schedule_simulation as sim
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}/simulations", tags=["simulations"])

EditKind = Literal["complete", "actual_start", "percent_complete", "remaining_duration", "finish_delay", "finish_on"]
_DATE_KINDS = {"complete", "actual_start", "finish_on"}


class SimEditIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=50)
    kind: EditKind
    # A date (YYYY-MM-DD) for complete / actual_start / finish_on, a number
    # otherwise: percent 0-100, or days in the activity's own calendar days.
    value: Optional[Union[float, str]] = None
    actual_start: Optional[date] = None


class SimRunIn(BaseModel):
    data_date: Optional[date] = None
    edits: list[SimEditIn] = Field(default_factory=list, max_length=sim.MAX_EDITS)
    # When the run is of a saved scenario, its last-run headline is updated.
    scenario_id: Optional[uuid.UUID] = None


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    simulation_data_date: Optional[date] = None
    edits: list[SimEditIn] = Field(default_factory=list, max_length=sim.MAX_EDITS)


class ScenarioPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    simulation_data_date: Optional[date] = None
    edits: Optional[list[SimEditIn]] = Field(default=None, max_length=sim.MAX_EDITS)


def _company_view(db: Session, project_id: uuid.UUID, ctx: AuthContext) -> None:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    if ctx.role == TenantRole.subcontractor:
        raise HTTPException(status_code=403, detail="Not permitted")
    require_project_permission(db, project_id, ctx)


def _company_edit(db: Session, project_id: uuid.UUID, ctx: AuthContext) -> None:
    _company_view(db, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)


def _to_edit(e: SimEditIn) -> sim.SimEdit:
    value: float | date | None
    if e.kind in _DATE_KINDS:
        if e.value in (None, ""):
            value = None
        else:
            try:
                value = date.fromisoformat(str(e.value)[:10])
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "invalid_edits",
                        "message": "Some changes can't be simulated.",
                        "errors": [{"external_id": e.external_id, "message": "Pick a valid date."}],
                    },
                )
    else:
        try:
            value = None if e.value in (None, "") else float(e.value)
        except (TypeError, ValueError):
            value = None
    return sim.SimEdit(external_id=e.external_id, kind=e.kind, value=value, actual_start=e.actual_start)


def _can_change(row: ScheduleSimulation, ctx: AuthContext) -> bool:
    return ctx.role == TenantRole.company_admin or row.created_by_user_id == ctx.user.id


def _load(db: Session, project_id: uuid.UUID, scenario_id: uuid.UUID, ctx: AuthContext) -> ScheduleSimulation:
    row = get_tenant_scoped_or_404(db, ScheduleSimulation, scenario_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return row


def _scenario_out(row: ScheduleSimulation, ctx: AuthContext, current_import_id: Optional[uuid.UUID], names: dict) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "simulation_data_date": row.simulation_data_date.isoformat() if row.simulation_data_date else None,
        "edits": row.edits or [],
        "schedule_import_id": str(row.schedule_import_id) if row.schedule_import_id else None,
        "revision_label": row.revision_label,
        # Made (last run) on an earlier import than the current one.
        "stale": row.schedule_import_id is not None and row.schedule_import_id != current_import_id,
        "last_finish_delta_days": row.last_finish_delta_days,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "created_by_name": names.get(row.created_by_user_id),
        "is_owner": row.created_by_user_id == ctx.user.id,
        "can_change": _can_change(row, ctx),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _names(db: Session, rows: list[ScheduleSimulation]) -> dict:
    ids = {r.created_by_user_id for r in rows if r.created_by_user_id}
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.query(User).filter(User.id.in_(ids))}


@router.get("/context")
def simulation_context(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> dict:
    """What the page builds a scenario from: the current data date and the
    current programme's activities as the live schedule shows them."""
    _company_view(db, project_id, ctx)
    current = get_current_import(db, ctx.tenant_id, project_id)
    dd = to_naive(current.data_date) if current is not None else None
    return {
        "has_schedule": current is not None,
        "import_id": str(current.id) if current is not None else None,
        "revision_label": current.revision_label if current is not None else None,
        "imported_at": current.imported_at.isoformat() if current is not None and current.imported_at else None,
        "current_data_date": dd.date().isoformat() if dd else None,
        "activities": sim.picker_activities(db, ctx.tenant_id, project_id) if current is not None else [],
    }


@router.post("/run")
def run_simulation(
    project_id: uuid.UUID,
    body: SimRunIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    _company_view(db, project_id, ctx)
    try:
        result = sim.run_simulation(db, ctx.tenant_id, project_id, body.data_date, [_to_edit(e) for e in body.edits])
    except sim.SimulationError as e:
        raise HTTPException(status_code=422, detail=e.detail())
    if body.scenario_id is not None:
        row = _load(db, project_id, body.scenario_id, ctx)
        if _can_change(row, ctx):
            row.last_finish_delta_days = result["project_finish"]["delta_days"]
            row.last_run_at = datetime.now(timezone.utc)
            row.schedule_import_id = uuid.UUID(result["import_id"])
            row.revision_label = result["revision_label"]
            db.commit()
    return result


@router.get("/scenarios")
def list_scenarios(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> list[dict]:
    _company_view(db, project_id, ctx)
    rows = (
        db.query(ScheduleSimulation)
        .filter(ScheduleSimulation.tenant_id == ctx.tenant_id, ScheduleSimulation.project_id == project_id)
        .order_by(ScheduleSimulation.updated_at.desc())
        .all()
    )
    current = get_current_import(db, ctx.tenant_id, project_id)
    names = _names(db, rows)
    # Your own scenarios first, then everyone else's — newest first within each.
    rows.sort(key=lambda r: r.created_by_user_id != ctx.user.id)
    return [_scenario_out(r, ctx, current.id if current else None, names) for r in rows]


@router.post("/scenarios", status_code=201)
def create_scenario(
    project_id: uuid.UUID,
    body: ScenarioIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    _company_edit(db, project_id, ctx)
    current = get_current_import(db, ctx.tenant_id, project_id)
    row = ScheduleSimulation(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        name=body.name.strip(),
        simulation_data_date=body.simulation_data_date,
        edits=[e.model_dump(mode="json") for e in body.edits],
        schedule_import_id=current.id if current else None,
        revision_label=current.revision_label if current else None,
        created_by_user_id=ctx.user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _scenario_out(row, ctx, current.id if current else None, _names(db, [row]))


@router.patch("/scenarios/{scenario_id}")
def update_scenario(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    body: ScenarioPatch,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    _company_edit(db, project_id, ctx)
    row = _load(db, project_id, scenario_id, ctx)
    if not _can_change(row, ctx):
        raise HTTPException(status_code=403, detail="Only whoever saved this scenario can change it")
    fields = body.model_fields_set
    if body.name is not None:
        row.name = body.name.strip()
    if "simulation_data_date" in fields:
        row.simulation_data_date = body.simulation_data_date
    if body.edits is not None:
        row.edits = [e.model_dump(mode="json") for e in body.edits]
    db.commit()
    db.refresh(row)
    current = get_current_import(db, ctx.tenant_id, project_id)
    return _scenario_out(row, ctx, current.id if current else None, _names(db, [row]))


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(
    project_id: uuid.UUID,
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> Response:
    _company_edit(db, project_id, ctx)
    row = _load(db, project_id, scenario_id, ctx)
    if not _can_change(row, ctx):
        raise HTTPException(status_code=403, detail="Only whoever saved this scenario can delete it")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
