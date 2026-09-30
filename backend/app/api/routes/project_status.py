import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    AuthContext,
    get_current_tenant_user,
    get_tenant_scoped_or_404,
    require_project_permission,
)
from app.engine.durations import activity_days
from app.models.activity import Activity
from app.models.activity_code import TaskActivityCode
from app.models.project import Project
from app.models.schedule_status_snapshot import ScheduleStatusSnapshot
from app.models.wbs_node import WbsNode
from app.services.schedule_current import to_naive
from app.schemas.project_status import (
    PrioritiesOut,
    PriorityActivityOut,
    PriorityQuadrantOut,
    ProjectStatusOut,
    StatusCardOut,
    StatusSummaryOut,
    StatusTrendPointOut,
)
from app.services import project_status as ps

router = APIRouter(prefix="/projects/{project_id}/status", tags=["project-status"])

_PREVIEW_LIMIT = 30
_HOURS_PER_DAY_FALLBACK = 8.0


def _descendant_wbs_ids(db: Session, tenant_id, project_id, root_wbs_id: str) -> set[str]:
    """The chosen WBS node plus every node under it (parent_wbs_id is a P6
    token, not an FK, so walk it in Python — WBS trees are small)."""
    nodes = (
        db.query(WbsNode)
        .filter(WbsNode.tenant_id == tenant_id, WbsNode.project_id == project_id)
        .all()
    )
    children: dict[str, list[str]] = {}
    for n in nodes:
        children.setdefault(n.parent_wbs_id or "", []).append(n.wbs_id)
    out: set[str] = set()
    stack = [root_wbs_id]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def _card(series: list[StatusTrendPointOut], verdict: str, headline: str) -> StatusCardOut:
    metric = series[-1].value if series else None
    delta = round(series[-1].value - series[-2].value, 3) if len(series) >= 2 else None
    return StatusCardOut(verdict=verdict, headline=headline, metric=metric, delta=delta, series=series)


@router.get("", response_model=ProjectStatusOut)
def get_project_status(
    project_id: uuid.UUID,
    wbs_id: str | None = Query(default=None),
    code_value_id: list[uuid.UUID] | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ProjectStatusOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    inputs = ps.load_status_inputs(db, ctx.tenant_id, project_id)
    rollup = ps.rollup_from_inputs(inputs)

    last_import = inputs["last_import"]
    hours_per_day = inputs["hours_per_day"] or _HOURS_PER_DAY_FALLBACK
    dd = (to_naive(last_import.data_date) if last_import else None) or datetime.utcnow()

    # --- trend series: stored snapshots + a live "current" point ---
    snapshots = (
        db.query(ScheduleStatusSnapshot)
        .filter(
            ScheduleStatusSnapshot.tenant_id == ctx.tenant_id,
            ScheduleStatusSnapshot.project_id == project_id,
        )
        .order_by(ScheduleStatusSnapshot.captured_at.asc())
        .all()
    )
    has_snapshots = len(snapshots) > 0
    latest_has_snapshot = last_import is not None and any(
        s.schedule_import_id == last_import.id for s in snapshots
    )

    live_values = {
        "spi": rollup.spi,
        "schedule_recovery_index": rollup.schedule_recovery_index,
        "dcma_score": rollup.dcma_score,
    }
    live_label = (last_import.revision_label if last_import else None) or "Current"

    def series_for(attr: str) -> list[StatusTrendPointOut]:
        points: list[StatusTrendPointOut] = []
        for s in snapshots:
            value = getattr(s, attr)
            if value is None:
                continue
            label = s.revision_label or s.captured_at.strftime("%d-%b")
            points.append(StatusTrendPointOut(label=label, value=round(value, 3)))
        if last_import is not None and not latest_has_snapshot:
            value = live_values[attr]
            if value is not None:
                points.append(StatusTrendPointOut(label=live_label, value=round(value, 3)))
        return points

    summary = StatusSummaryOut(
        progress=_card(
            series_for("spi"),
            rollup.progress_verdict,
            f"SPI {rollup.spi:.2f}" if rollup.spi is not None else "No progress data",
        ),
        risk=_card(
            series_for("schedule_recovery_index"),
            rollup.risk_verdict,
            f"{rollup.schedule_recovery_index:.2f}× uplift required"
            if rollup.schedule_recovery_index is not None
            else f"{rollup.negative_float_count} activities behind",
        ),
        quality=_card(
            series_for("dcma_score"),
            rollup.quality_verdict,
            f"{rollup.dcma_score:.1f}% quality score",
        ),
    )

    # --- priorities matrix: filter, then bucket ---
    activities: list[Activity] = ps.real_activities(inputs["activities"])

    if wbs_id:
        keep_wbs = _descendant_wbs_ids(db, ctx.tenant_id, project_id, wbs_id)
        activities = [a for a in activities if a.wbs_path in keep_wbs]
    if code_value_id:
        wanted = set(code_value_id)
        coded_activity_ids = {
            row.activity_id
            for row in db.query(TaskActivityCode.activity_id, TaskActivityCode.code_value_id).filter(
                TaskActivityCode.tenant_id == ctx.tenant_id,
                TaskActivityCode.project_id == project_id,
                TaskActivityCode.code_value_id.in_(wanted),
            )
        }
        activities = [a for a in activities if a.id in coded_activity_ids]
    if q:
        needle = q.strip().lower()
        activities = [
            a for a in activities if needle in a.name.lower() or needle in a.external_id.lower()
        ]

    buckets: dict[str, list[Activity]] = {key: [] for key, *_ in ps.QUADRANTS}
    for a in activities:
        buckets[ps.quadrant_key(a, dd, hours_per_day)].append(a)

    flagged = rollup.dcma_flagged_external_ids

    def to_row(a: Activity) -> PriorityActivityOut:
        tf = activity_days(a, a.total_float_hours, hours_per_day)
        tf_days = round(tf, 1) if tf is not None else None
        return PriorityActivityOut(
            activity_id=a.id,
            external_id=a.external_id,
            name=a.name,
            discipline=a.discipline,
            planned_start=a.planned_start,
            planned_finish=a.planned_finish,
            total_float_days=tf_days,
            percent_complete=a.percent_complete or 0,
            is_critical=bool(a.is_critical),
            is_overdue=ps.is_overdue(a, dd),
            is_delay_driver=a.total_float_hours is not None and a.total_float_hours < 0,
        )

    quadrants: list[PriorityQuadrantOut] = []
    preview: dict[str, list[PriorityActivityOut]] = {}
    for key, label, *_ in ps.QUADRANTS:
        rows = buckets[key]
        program = [a for a in rows if a.last_import_id is not None]
        users = [a for a in rows if a.last_import_id is None]
        recs = sum(1 for a in rows if a.external_id in flagged)
        quadrants.append(
            PriorityQuadrantOut(
                key=key,
                label=label,
                program_count=len(program),
                user_count=len(users),
                recommendation_count=recs,
            )
        )
        ordered = sorted(
            rows,
            key=lambda a: (
                not ps.is_overdue(a, dd),
                a.total_float_hours if a.total_float_hours is not None else 1e9,
                a.planned_finish or a.planned_start or dd.date(),
            ),
        )
        preview[key] = [to_row(a) for a in ordered[:_PREVIEW_LIMIT]]

    return ProjectStatusOut(
        project_id=project_id,
        data_date=to_naive(last_import.data_date) if last_import else None,
        latest_revision_label=last_import.revision_label if last_import else None,
        latest_filename=last_import.filename if last_import else None,
        imported_at=last_import.imported_at if last_import else None,
        has_snapshots=has_snapshots,
        summary=summary,
        priorities=PrioritiesOut(
            quadrants=quadrants,
            activities=preview,
            filtered_total=len(activities),
        ),
    )
