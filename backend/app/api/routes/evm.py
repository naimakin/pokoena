import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission, require_role
from app.engine.cpm.calendar_engine import NoWorkingDayError
from app.engine.cpm.scheduler import CpmCycleError
from app.engine.evm.evm_engine import calculate_evm
from app.engine.evm.excel_export import build_evm_excel
from app.engine.evm.scurve_engine import (
    aggregate_granularity,
    compute_current_ev,
    compute_evm_series,
    find_out_of_sequence_activities,
)
from app.engine.evm.variance_engine import compute_baseline_date_variance
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.baseline import (
    Baseline,
    BaselineActivity,
    BaselinePvCurve,
    BaselineResource,
    BaselineResourceAssignment,
    BaselineStatus,
)
from app.models.calendar import Calendar
from app.models.evm_snapshot import EvmSnapshot
from app.models.progress_entry import ProgressEntry, ProgressEntryType
from app.models.project import Project
from app.models.resource import LABOR, MATERIAL, NONLABOR
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_import import ScheduleImport
from app.models.user_tenant_role import TenantRole
from app.parser.xer_parser import XerParseError
from app.services.baseline import (
    BaselineConflictError,
    BaselineValidationError,
    lock_baseline_for_project,
    lock_baseline_from_snapshot,
)
from app.services.xer_import import DataDateRegressionError, import_xer
from app.schemas.evm import (
    BaselineOut,
    BaselineProgramResultOut,
    BaselineResourceItemOut,
    BaselineResourceSummaryOut,
    BaselineStatusOut,
    BaselineVarianceOut,
    EvmScurveOut,
    EvmScurvePointOut,
    EvmSummaryOut,
    LockBaselineRequest,
    LockBaselineResultOut,
    ProgressBatchIn,
    ProgressCurveOut,
    ProgressCurvePointOut,
    ProgressEntryOut,
    ProgressSubmitResultOut,
    ProgressSummaryOut,
    ProgressVersionOut,
    QuickEvmOut,
)
from app.services.progress_summary import (
    PROGRESS_BASIS,
    compute_progress_curve,
    compute_progress_summary,
    evm_point_at,
)
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}/evm", tags=["evm"])


@router.get("/quick", response_model=QuickEvmOut)
def get_quick_evm(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> QuickEvmOut:
    """Live EVM computed from the project's current schedule and resource
    assignments — no baseline required. See engine/evm/evm_engine.py."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    assignments = (
        db.query(ResourceAssignment)
        .filter(ResourceAssignment.tenant_id == ctx.tenant_id, ResourceAssignment.project_id == project_id)
        .all()
    )
    calendars = db.query(Calendar).filter(Calendar.tenant_id == ctx.tenant_id, Calendar.project_id == project_id).all()

    last_import = get_current_import(db, ctx.tenant_id, project_id)
    data_date = to_naive(last_import.data_date) if last_import else None

    result = calculate_evm(activities, assignments, calendars, data_date)
    return QuickEvmOut.model_validate(result)


# ---------------------------------------------------------------------------
# Phase B: baseline lock + S-curve time series
#
# "Vance Baseline Mandate" (reference project's term for at-most-one-active-
# baseline immutability) is enforced here at the application layer instead of
# a DB trigger — see app/models/baseline.py's docstring for why. The only
# routes that ever mutate a `baselines` row are lock (INSERT) and supersede
# (a single status flip); nothing exposes a generic update, so the guarantee
# holds without trigger machinery this codebase doesn't use anywhere else.
#
# PV-curve generation and EVM-snapshot recalculation run synchronously in the
# request instead of the reference's FastAPI BackgroundTasks — same
# simplification already made for Monte Carlo/DCMA at this project's scale.
# ---------------------------------------------------------------------------


def _require_active_baseline(db: Session, ctx: AuthContext, project_id: uuid.UUID) -> Baseline:
    baseline = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == ctx.tenant_id, Baseline.project_id == project_id, Baseline.status == BaselineStatus.active)
        .first()
    )
    if baseline is None:
        raise HTTPException(
            status_code=423,
            detail={
                "code": "BASELINE_NOT_ACTIVE",
                "message": "No active Performance Measurement Baseline exists for this project. "
                "Lock a baseline before accessing EVM metrics.",
                "action_required": "lock_baseline",
            },
        )
    return baseline


def _load_pv_ac_series(db: Session, project_id: uuid.UUID, baseline_id: uuid.UUID):
    pv_rows = db.query(BaselinePvCurve).filter(BaselinePvCurve.baseline_id == baseline_id).all()
    pv_series = {r.curve_date: r.pv_cumulative for r in pv_rows}

    ac_rows = (
        db.query(ProgressEntry.entry_date, func.sum(ProgressEntry.burned_manhours_daily))
        .filter(
            ProgressEntry.project_id == project_id,
            ProgressEntry.entry_type.in_([ProgressEntryType.actual, ProgressEntryType.correction]),
        )
        .group_by(ProgressEntry.entry_date)
        .order_by(ProgressEntry.entry_date)
        .all()
    )
    running = 0.0
    ac_series: dict = {}
    for entry_date, daily in ac_rows:
        running += float(daily)
        ac_series[entry_date] = round(running, 4)

    return pv_series, ac_series


def _recalculate_evm_snapshots(db: Session, ctx: AuthContext, project_id: uuid.UUID, baseline: Baseline) -> None:
    pv_series, ac_series = _load_pv_ac_series(db, project_id, baseline.id)
    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    current_ev = compute_current_ev(activities)

    points = compute_evm_series(pv_series, ac_series, baseline.total_budget_manhours, current_ev)

    existing_by_date = {
        row.snapshot_date: row
        for row in db.query(EvmSnapshot)
        .filter(EvmSnapshot.project_id == project_id, EvmSnapshot.baseline_id == baseline.id)
        .all()
    }
    for p in points:
        row = existing_by_date.get(p.snapshot_date)
        if row is None:
            row = EvmSnapshot(
                id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=project_id, baseline_id=baseline.id,
                snapshot_date=p.snapshot_date,
            )
            db.add(row)
        row.pv_cumulative = p.pv_cumulative
        row.ev_cumulative = p.ev_cumulative
        row.ac_cumulative = p.ac_cumulative
        row.spi = p.spi
        row.cpi = p.cpi
        row.sv = p.sv
        row.cv = p.cv
        row.bac = p.bac
        row.eac = p.eac
        row.etc = p.etc
        row.tcpi = p.tcpi
        row.percent_complete_planned = p.percent_complete_planned
        row.percent_complete_earned = p.percent_complete_earned
    db.flush()


def _baseline_out(db: Session, baseline: Baseline) -> BaselineOut:
    """BaselineOut with `source_filename` resolved from the .xer it was locked
    from — the UI shows "locked from update_2026_08.xer" rather than a UUID."""
    out = BaselineOut.model_validate(baseline)
    si = db.get(ScheduleImport, baseline.schedule_import_id)
    out.source_filename = si.filename if si else None
    return out


def _unique_baseline_label(db: Session, project_id: uuid.UUID) -> str:
    existing = {
        b.version_label
        for b in db.query(Baseline.version_label).filter(Baseline.project_id == project_id).all()
    }
    if "Baseline" not in existing:
        return "Baseline"
    n = 2
    while f"Baseline r{n}" in existing:
        n += 1
    return f"Baseline r{n}"


@router.get("/baseline", response_model=BaselineStatusOut)
def get_baseline_status(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> BaselineStatusOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    baselines = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == ctx.tenant_id, Baseline.project_id == project_id)
        .order_by(Baseline.created_at.desc())
        .all()
    )
    active = next((b for b in baselines if b.status == BaselineStatus.active), None)
    return BaselineStatusOut(
        project_id=project_id,
        has_active=active is not None,
        active_baseline=_baseline_out(db, active) if active else None,
        all_baselines=[_baseline_out(db, b) for b in baselines],
    )


@router.post("/baseline/program", response_model=BaselineProgramResultOut, status_code=201)
def upload_baseline_program(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    force: bool = Form(False),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> BaselineProgramResultOut:
    """Upload the baseline programme (.xer) from Planning → Baselines. First
    use of this endpoint (or the Program Library) locks the baseline; every
    later upload here overwrites it in place (same baseline row, recomputed
    activities / PV curve / frozen resources — the owner's choice over
    versioning). Also refreshes EVM snapshots when progress already exists so
    a replace doesn't leave stale metrics.

    Unless this is the project's very first import ever (nothing else to be
    "current" yet), the baseline is locked/overwritten from THIS file's own
    parsed data and the project's live activities/relationships/"Current
    update" are left completely untouched — see the `baseline_non_destructive`
    path in services/xer_import.py. Re-uploading an (usually older) baseline
    file can therefore no longer silently regress or reclassify the live
    schedule, so `force` only matters for that first-import case now."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)

    if not file.filename or not file.filename.lower().endswith(".xer"):
        raise HTTPException(status_code=400, detail="Only .xer files are supported")

    had_active_baseline = (
        db.query(Baseline)
        .filter(
            Baseline.tenant_id == ctx.tenant_id,
            Baseline.project_id == project_id,
            Baseline.status == BaselineStatus.active,
        )
        .first()
        is not None
    )

    file_bytes = file.file.read()
    try:
        schedule_import = import_xer(
            db, project_id, ctx, file.filename, file_bytes, revision_kind="baseline", force=force
        )
    except XerParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CpmCycleError as e:
        raise HTTPException(
            status_code=400,
            detail=f"This schedule can't be recomputed: {e} Fix the circular dependency in P6 and re-export.",
        )
    except NoWorkingDayError as e:
        raise HTTPException(status_code=400, detail=f"This schedule can't be recomputed: {e}")
    except DataDateRegressionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except BaselineValidationError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except BaselineConflictError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

    # import_xer already locked or overwrote the active baseline internally
    # (from the live tables on a project's first-ever import, otherwise from
    # this file's own parsed data — never both, see baseline_non_destructive).
    baseline = (
        db.query(Baseline)
        .filter(
            Baseline.tenant_id == ctx.tenant_id,
            Baseline.project_id == project_id,
            Baseline.status == BaselineStatus.active,
        )
        .first()
    )
    if baseline is None:
        raise HTTPException(status_code=422, detail="This schedule can't be locked as a baseline yet.")
    mode = "overwritten" if had_active_baseline else "created"
    if mode == "overwritten" and db.query(ProgressEntry).filter(ProgressEntry.project_id == project_id).first() is not None:
        _recalculate_evm_snapshots(db, ctx, project_id, baseline)
        db.commit()

    db.refresh(baseline)
    return BaselineProgramResultOut(
        mode=mode,
        filename=schedule_import.filename,
        activity_count=schedule_import.activity_count,
        critical_count=schedule_import.critical_count,
        warnings=schedule_import.warnings,
        baseline=_baseline_out(db, baseline),
    )


@router.get("/baseline/resources", response_model=BaselineResourceSummaryOut)
def get_baseline_resources(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> BaselineResourceSummaryOut:
    """The P6 resources frozen against the active baseline, with budgeted
    quantity/cost rolled up per resource from the frozen TASKRSRC lines."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    baseline = _require_active_baseline(db, ctx, project_id)

    resources = (
        db.query(BaselineResource).filter(BaselineResource.baseline_id == baseline.id).all()
    )
    assignments = (
        db.query(BaselineResourceAssignment)
        .filter(BaselineResourceAssignment.baseline_id == baseline.id)
        .all()
    )

    qty_by_rsrc: dict[uuid.UUID, float] = {}
    cost_by_rsrc: dict[uuid.UUID, float] = {}
    count_by_rsrc: dict[uuid.UUID, int] = {}
    for a in assignments:
        qty_by_rsrc[a.baseline_resource_id] = qty_by_rsrc.get(a.baseline_resource_id, 0.0) + (a.target_qty or 0.0)
        cost_by_rsrc[a.baseline_resource_id] = cost_by_rsrc.get(a.baseline_resource_id, 0.0) + (a.target_cost or 0.0)
        count_by_rsrc[a.baseline_resource_id] = count_by_rsrc.get(a.baseline_resource_id, 0) + 1

    items = [
        BaselineResourceItemOut(
            rsrc_id=r.rsrc_id, name=r.name, short_name=r.short_name, rsrc_type=r.rsrc_type, unit_id=r.unit_id,
            budgeted_qty=round(qty_by_rsrc.get(r.id, 0.0), 2), budgeted_cost=round(cost_by_rsrc.get(r.id, 0.0), 2),
            assignment_count=count_by_rsrc.get(r.id, 0),
        )
        for r in resources
    ]
    items.sort(key=lambda i: (i.rsrc_type, i.name))

    return BaselineResourceSummaryOut(
        project_id=project_id,
        baseline_id=baseline.id,
        version_label=baseline.version_label,
        resource_count=len(resources),
        labor_count=sum(1 for r in resources if r.rsrc_type == LABOR),
        material_count=sum(1 for r in resources if r.rsrc_type == MATERIAL),
        equipment_count=sum(1 for r in resources if r.rsrc_type == NONLABOR),
        total_budgeted_labor_hours=round(
            sum(qty_by_rsrc.get(r.id, 0.0) for r in resources if r.rsrc_type == LABOR), 2
        ),
        total_budgeted_cost=round(sum(cost_by_rsrc.values()), 2),
        resources=items,
    )


@router.get("/baseline/variance", response_model=BaselineVarianceOut)
def get_baseline_variance(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> BaselineVarianceOut:
    """Baseline (frozen) vs current schedule (latest update-programme import):
    per-activity start/finish date variance in calendar days, plus a
    project-level slip summary and a distribution histogram for the chart."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    baseline = _require_active_baseline(db, ctx, project_id)

    baseline_activities = (
        db.query(BaselineActivity).filter(BaselineActivity.baseline_id == baseline.id).all()
    )
    activities_by_id = {
        a.id: a
        for a in db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    }

    result = compute_baseline_date_variance(baseline_activities, activities_by_id)
    return BaselineVarianceOut(
        project_id=project_id,
        baseline_id=baseline.id,
        version_label=baseline.version_label,
        summary=result["summary"],
        rows=result["rows"],
    )


@router.post("/baseline", response_model=LockBaselineResultOut, status_code=201)
def lock_baseline(
    project_id: uuid.UUID,
    payload: LockBaselineRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> LockBaselineResultOut:
    """Locks the project's CURRENT schedule as a baseline — we don't keep
    versioned historical schedule snapshots (see services/xer_import.py), so
    unlike the reference (which locks a specific named snapshot), this always
    locks "now". The actual lock (BAC/date computation, Baseline/
    BaselineActivity/BaselinePvCurve writes) lives in services/baseline.py,
    shared with the Program Library page's auto-lock-on-first-import."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)

    last_import = get_current_import(db, ctx.tenant_id, project_id)
    if last_import is None:
        raise HTTPException(status_code=422, detail="No schedule has been imported for this project yet.")

    try:
        baseline = lock_baseline_for_project(
            db, ctx.tenant_id, project_id, last_import.id, ctx.user.id,
            version_label=payload.version_label, notes=payload.notes,
        )
    except BaselineValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except BaselineConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.commit()

    return LockBaselineResultOut(
        status="locked", baseline_id=baseline.id, version_label=baseline.version_label,
        bac=round(baseline.total_budget_manhours, 2), activity_count=baseline.activity_count,
        target_start=baseline.target_start_date, target_end=baseline.target_end_date,
    )


@router.post("/baseline/from-import/{import_id}", response_model=LockBaselineResultOut, status_code=201)
def set_baseline_from_import(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> LockBaselineResultOut:
    """Program Library: make the chosen import the project's baseline, replacing
    the active one (which is kept as `superseded`, not deleted). If this import
    was the baseline before, that exact frozen baseline is restored, including its
    resources and EVM history, so an unlock is fully reversible. Otherwise a new
    baseline is frozen from it: from the live schedule when it is the current
    update, else from its saved activity snapshot (no resources, see
    lock_baseline_from_snapshot)."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    schedule_import = get_tenant_scoped_or_404(db, ScheduleImport, import_id, ctx)
    if schedule_import.project_id != project_id:
        raise HTTPException(status_code=404, detail="ScheduleImport not found")

    baselines = db.query(Baseline).filter(Baseline.tenant_id == ctx.tenant_id, Baseline.project_id == project_id)
    active = baselines.filter(Baseline.status == BaselineStatus.active).first()
    if active is None or active.schedule_import_id != import_id:
        restorable = (
            baselines.filter(Baseline.status == BaselineStatus.superseded, Baseline.schedule_import_id == import_id)
            .order_by(Baseline.created_at.desc())
            .first()
        )
        if active is not None:
            active.status = BaselineStatus.superseded
            db.flush()
        if restorable is not None:
            restorable.status = BaselineStatus.active
            active = restorable
        else:
            current = get_current_import(db, ctx.tenant_id, project_id)
            label = _unique_baseline_label(db, project_id)
            try:
                if current is not None and current.id == import_id:
                    active = lock_baseline_for_project(
                        db, ctx.tenant_id, project_id, import_id, ctx.user.id, version_label=label
                    )
                else:
                    active = lock_baseline_from_snapshot(
                        db, ctx.tenant_id, project_id, schedule_import, ctx.user.id, label
                    )
            except BaselineValidationError as e:
                db.rollback()
                raise HTTPException(status_code=422, detail=str(e))
            except BaselineConflictError as e:
                db.rollback()
                raise HTTPException(status_code=409, detail=str(e))
        if db.query(ProgressEntry).filter(ProgressEntry.project_id == project_id).first() is not None:
            _recalculate_evm_snapshots(db, ctx, project_id, active)
        db.commit()
        db.refresh(active)

    return LockBaselineResultOut(
        status="locked", baseline_id=active.id, version_label=active.version_label,
        bac=round(active.total_budget_manhours, 2), activity_count=active.activity_count,
        target_start=active.target_start_date, target_end=active.target_end_date,
    )


@router.delete("/baseline/{baseline_id}")
def supersede_baseline(
    project_id: uuid.UUID,
    baseline_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> dict:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    baseline = get_tenant_scoped_or_404(db, Baseline, baseline_id, ctx)
    if baseline.project_id != project_id:
        raise HTTPException(status_code=400, detail="Baseline does not belong to this project")
    if baseline.status != BaselineStatus.active:
        raise HTTPException(status_code=409, detail=f"Baseline is not active (status={baseline.status.value}).")

    baseline.status = BaselineStatus.superseded
    db.commit()
    return {"status": "superseded", "baseline_id": str(baseline_id)}


@router.post("/progress", response_model=ProgressSubmitResultOut)
def submit_progress(
    project_id: uuid.UUID,
    payload: ProgressBatchIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ProgressSubmitResultOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)
    baseline = _require_active_baseline(db, ctx, project_id)

    project_activity_ids = {
        row.id for row in db.query(Activity.id).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    }

    written = 0
    for entry in payload.entries:
        if entry.activity_id not in project_activity_ids:
            raise HTTPException(status_code=400, detail=f"Activity {entry.activity_id} does not belong to this project")

        existing = (
            db.query(ProgressEntry)
            .filter(
                ProgressEntry.project_id == project_id,
                ProgressEntry.activity_id == entry.activity_id,
                ProgressEntry.entry_date == entry.entry_date,
            )
            .first()
        )
        if existing:
            existing.burned_manhours_daily = entry.burned_manhours_daily
            existing.physical_pct_snapshot = entry.physical_pct_snapshot
            existing.crew_size = entry.crew_size
            existing.notes = entry.notes
            existing.entry_type = ProgressEntryType.correction
        else:
            db.add(
                ProgressEntry(
                    id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=project_id, activity_id=entry.activity_id,
                    entry_date=entry.entry_date, burned_manhours_daily=entry.burned_manhours_daily,
                    physical_pct_snapshot=entry.physical_pct_snapshot, crew_size=entry.crew_size, notes=entry.notes,
                    created_by_user_id=ctx.user.id,
                )
            )
        written += 1
    db.flush()

    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    relationships = (
        db.query(ActivityRelationship)
        .filter(ActivityRelationship.tenant_id == ctx.tenant_id, ActivityRelationship.project_id == project_id)
        .all()
    )
    reported_ids = {
        row.activity_id
        for row in db.query(ProgressEntry.activity_id).filter(ProgressEntry.project_id == project_id).all()
    }
    out_of_sequence_ids = find_out_of_sequence_activities(activities, relationships, reported_ids)
    if out_of_sequence_ids:
        db.query(ProgressEntry).filter(
            ProgressEntry.project_id == project_id, ProgressEntry.activity_id.in_(out_of_sequence_ids)
        ).update({"is_out_of_sequence": True}, synchronize_session=False)

    _recalculate_evm_snapshots(db, ctx, project_id, baseline)

    db.commit()
    return ProgressSubmitResultOut(status="accepted", written=written, out_of_sequence_count=len(out_of_sequence_ids))


@router.get("/progress", response_model=list[ProgressEntryOut])
def list_progress(
    project_id: uuid.UUID,
    activity_id: uuid.UUID | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[ProgressEntry]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    query = db.query(ProgressEntry).filter(ProgressEntry.tenant_id == ctx.tenant_id, ProgressEntry.project_id == project_id)
    if activity_id:
        query = query.filter(ProgressEntry.activity_id == activity_id)
    return query.order_by(ProgressEntry.entry_date.desc()).limit(limit).all()


@router.get("/scurve", response_model=EvmScurveOut)
def get_scurve(
    project_id: uuid.UUID,
    granularity: str = "weekly",
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> EvmScurveOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    baseline = _require_active_baseline(db, ctx, project_id)

    pv_series, ac_series = _load_pv_ac_series(db, project_id, baseline.id)
    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    current_ev = compute_current_ev(activities)

    points = compute_evm_series(pv_series, ac_series, baseline.total_budget_manhours, current_ev)
    series = aggregate_granularity(points, granularity)

    return EvmScurveOut(
        project_id=project_id, baseline_id=baseline.id, version_label=baseline.version_label,
        bac=round(baseline.total_budget_manhours, 2), granularity=granularity, points=len(series),
        series=[
            EvmScurvePointOut(
                date=p.snapshot_date.isoformat(), pv=p.pv_cumulative, ev=p.ev_cumulative, ac=p.ac_cumulative, bac=p.bac,
                spi=p.spi, cpi=p.cpi, sv=p.sv, cv=p.cv, eac=p.eac, etc=p.etc, tcpi=p.tcpi,
                pct_planned=p.percent_complete_planned, pct_earned=p.percent_complete_earned, tcpi_critical=p.tcpi_critical,
            )
            for p in series
        ],
    )


@router.get("/summary", response_model=EvmSummaryOut)
def get_evm_summary(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> EvmSummaryOut:
    """EVM at the current schedule's data date — computed live (see
    services/progress_summary.py::evm_point_at for why not from the newest
    snapshot row)."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    baseline = _require_active_baseline(db, ctx, project_id)

    total_ac = (
        db.query(func.coalesce(func.sum(ProgressEntry.burned_manhours_daily), 0.0))
        .filter(
            ProgressEntry.project_id == project_id,
            ProgressEntry.entry_type.in_([ProgressEntryType.actual, ProgressEntryType.correction]),
        )
        .scalar()
    )
    entry_count = db.query(ProgressEntry).filter(ProgressEntry.project_id == project_id).count()
    p = evm_point_at(db, ctx.tenant_id, project_id, baseline)
    # Per PMI Practice Standard for EVM: before any work is performed, SPI=1.0
    # and CPI=1.0 — no deviation exists to measure (EvmPoint.compute).
    initialized = p.ev_cumulative == 0 and p.ac_cumulative == 0

    return EvmSummaryOut(
        project_id=project_id, baseline_id=baseline.id, version_label=baseline.version_label,
        status="baseline_initialized" if initialized else "active",
        message="Baseline locked. No progress recorded yet — indices start at 1.0 (PMI standard)." if initialized else None,
        as_of_date=p.snapshot_date, bac=round(baseline.total_budget_manhours, 2),
        pv_cumulative=p.pv_cumulative, ev_cumulative=p.ev_cumulative, ac_cumulative=p.ac_cumulative,
        spi=p.spi, cpi=p.cpi, sv=p.sv, cv=p.cv, eac=p.eac, etc=p.etc, tcpi=p.tcpi,
        tcpi_critical=p.tcpi_critical, pct_planned=p.percent_complete_planned,
        pct_earned=p.percent_complete_earned, total_ac_raw=round(float(total_ac or 0), 2), entry_count=entry_count,
    )


@router.get("/progress-summary", response_model=ProgressSummaryOut)
def get_progress_summary(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> ProgressSummaryOut:
    """Planned vs actual % at the data date (duration-weighted, LOE/WBS out)
    and the baseline vs latest version table. See engine/evm/progress_engine.py."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    baseline = _require_active_baseline(db, ctx, project_id)

    s = compute_progress_summary(db, ctx.tenant_id, project_id, baseline)

    def version(kind: str, label, imp: ScheduleImport | None, facts) -> ProgressVersionOut:
        return ProgressVersionOut(
            kind=kind, label=label, filename=imp.filename if imp else None,
            data_date=to_naive(imp.data_date).date() if imp and imp.data_date else None,
            start=facts.start, finish=facts.finish,
            milestones_total=facts.milestones_total, milestones_remaining=facts.milestones_remaining,
            tasks_total=facts.tasks_total, tasks_remaining=facts.tasks_remaining, max_wbs_level=facts.max_wbs_level,
        )

    return ProgressSummaryOut(
        project_id=project_id, baseline_id=baseline.id, version_label=baseline.version_label,
        data_date=s.data_date, basis=PROGRESS_BASIS,
        planned_pct=s.planned_pct, actual_pct=s.actual_pct, spi=s.spi,
        finish_variance_days=s.finish_variance_days,
        versions=[
            version("baseline", baseline.version_label, s.baseline_import, s.baseline_facts),
            version(
                "latest", s.current_import.revision_label if s.current_import else None,
                s.current_import, s.latest_facts,
            ),
        ],
    )


@router.get("/progress-curve", response_model=ProgressCurveOut)
def get_progress_curve(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> ProgressCurveOut:
    """Monthly planned / actual / forecast % complete — the progress S-curve.
    Same basis as /progress-summary (engine/evm/progress_engine.py)."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    baseline = _require_active_baseline(db, ctx, project_id)

    data_date, points = compute_progress_curve(db, ctx.tenant_id, project_id, baseline)
    return ProgressCurveOut(
        project_id=project_id, baseline_id=baseline.id, version_label=baseline.version_label, data_date=data_date,
        points=[
            ProgressCurvePointOut(date=p.date, planned=p.planned, actual=p.actual, forecast=p.forecast)
            for p in points
        ],
    )


@router.get("/export")
def export_evm_excel(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> Response:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    baseline = _require_active_baseline(db, ctx, project_id)

    snapshot_rows = (
        db.query(EvmSnapshot)
        .filter(EvmSnapshot.project_id == project_id, EvmSnapshot.baseline_id == baseline.id)
        .order_by(EvmSnapshot.snapshot_date.asc())
        .all()
    )
    snapshots = [
        {
            "snapshot_date": s.snapshot_date.isoformat(),
            "pv_cumulative": s.pv_cumulative,
            "ev_cumulative": s.ev_cumulative,
            "ac_cumulative": s.ac_cumulative,
            "sv": s.sv,
            "cv": s.cv,
            "percent_complete_planned": s.percent_complete_planned,
            "percent_complete_earned": s.percent_complete_earned,
            "eac": s.eac,
            "tcpi": s.tcpi,
            "spi": s.spi,
            "cpi": s.cpi,
        }
        for s in snapshot_rows
    ]

    baseline_activity_rows = (
        db.query(BaselineActivity, Activity)
        .join(Activity, Activity.id == BaselineActivity.activity_id)
        .filter(BaselineActivity.baseline_id == baseline.id)
        .all()
    )
    activities = [
        {
            "task_code": act.external_id,
            "task_name": act.name,
            "wbs_code": ba.wbs_code,
            "planned_manhours": ba.planned_manhours,
            "baseline_start": ba.baseline_start.isoformat() if ba.baseline_start else "",
            "baseline_end": ba.baseline_end.isoformat() if ba.baseline_end else "",
        }
        for ba, act in baseline_activity_rows
    ]

    project_info = {
        "name": project.name,
        "baseline_version": baseline.version_label,
        "bac": round(baseline.total_budget_manhours, 2),
        "target_start": baseline.target_start_date.isoformat(),
        "target_end": baseline.target_end_date.isoformat(),
        "locked_at": baseline.locked_at.isoformat() if baseline.locked_at else "",
    }

    xlsx_bytes = build_evm_excel(project_info, snapshots, activities)
    filename = f"Poko_EVM_{project.code}_{datetime.utcnow().date().isoformat()}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
