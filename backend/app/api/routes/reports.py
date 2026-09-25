"""Reporting: the block catalogue, saved report formats, and the header every
report carries.

A report format is a named selection of blocks — the same
`[{key, order, enabled, options}]` shape as a dashboard layout, against a
server-side catalogue. Every block renders from an endpoint that already
exists; nothing here computes schedule data itself.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.baseline import Baseline, BaselineStatus
from app.models.project import Project
from app.models.report_format import ReportFormat
from app.schemas.report import (
    ReportBlockCatalogueOut,
    ReportBlockConfig,
    ReportFormatCreate,
    ReportFormatOut,
    ReportFormatUpdate,
    ReportHeaderOut,
)
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}", tags=["reporting"])

# How Poko arrives at percent complete, stated on every report. See
# engine/evm/scurve_engine.py::compute_current_ev.
PROGRESS_BASIS = "Duration-weighted earned progress against the locked baseline"


# ---------------------------------------------------------------------------
# Block catalogue — the single source of truth for what a report can contain.
# The frontend registry must stay in sync (components/reporting/ReportBlocks.tsx),
# same contract as the dashboard widget registry.
# ---------------------------------------------------------------------------

BLOCK_CATALOGUE: list[ReportBlockCatalogueOut] = [
    ReportBlockCatalogueOut(
        key="cover",
        title="Cover page",
        description="Project, contract reference, data date, schedule revision and sign-off lines.",
    ),
    ReportBlockCatalogueOut(
        key="executive-summary",
        title="Executive summary",
        description="Your narrative, with the computed verdicts alongside it. Edit the text on the format.",
    ),
    ReportBlockCatalogueOut(
        key="milestones",
        title="Key dates and milestones",
        description="Milestone forecast against baseline, with variance in days.",
        requires="baseline",
    ),
    ReportBlockCatalogueOut(
        key="progress-vs-plan",
        title="Progress: planned vs actual",
        description="Planned and earned percent complete with SPI, CPI, SV and CV.",
        requires="baseline",
    ),
    ReportBlockCatalogueOut(
        key="s-curve",
        title="S-curve",
        description="Cumulative planned value, earned value and actual cost over time.",
        requires="baseline",
        default_options={"granularity": "monthly"},
    ),
    ReportBlockCatalogueOut(
        key="wbs-progress",
        title="Progress by WBS",
        description="Percent complete rolled up per WBS branch.",
    ),
    ReportBlockCatalogueOut(
        key="critical-path",
        title="Critical path",
        description="The driving activities to project finish, with remaining duration and total float.",
        default_options={"limit": 30},
    ),
    ReportBlockCatalogueOut(
        key="float-paths",
        title="Float paths",
        description="Paths 1..N into the completion milestone and the acceleration headroom between them.",
        default_options={"path_count": 3},
    ),
    ReportBlockCatalogueOut(
        key="baseline-variance",
        title="Baseline variance",
        description="Activities whose dates moved against the baseline, worst first.",
        requires="baseline",
        default_options={"limit": 25},
    ),
    ReportBlockCatalogueOut(
        key="schedule-changes",
        title="Schedule changes",
        description="What was added, removed, re-logicked or re-dated since the previous update.",
        requires="two_imports",
    ),
    ReportBlockCatalogueOut(
        key="lookahead",
        title="Lookahead",
        description="Activities starting or finishing inside the window, from the data date.",
        default_options={"weeks": 3},
    ),
    ReportBlockCatalogueOut(
        key="risk-top",
        title="Top risks",
        description="The highest-scoring open risks with owner and mitigation status.",
        default_options={"count": 5},
    ),
    ReportBlockCatalogueOut(
        key="monte-carlo",
        title="Probabilistic finish",
        description="P50 / P80 completion from the Monte Carlo run, against the deterministic date.",
    ),
    ReportBlockCatalogueOut(
        key="dcma",
        title="DCMA 14-point check",
        description="Schedule quality score with each check's pass, warn or fail.",
    ),
]

BLOCK_KEYS = tuple(b.key for b in BLOCK_CATALOGUE)
_DEFAULT_OPTIONS = {b.key: b.default_options for b in BLOCK_CATALOGUE}


def _preset(name: str, description: str, keys: list[str], orientation: str = "portrait") -> dict:
    return {
        "name": name,
        "description": description,
        "page_setup": {"orientation": orientation, "paper": "A4"},
        "blocks": [
            {"key": key, "order": i, "enabled": True, "options": dict(_DEFAULT_OPTIONS.get(key, {}))}
            for i, key in enumerate(keys)
        ],
    }


# The four reports a construction project actually issues. Seeded per project on
# first read rather than by migration, so projects that already existed get them
# too, and so a team can delete the ones they don't use.
PRESETS: list[dict] = [
    _preset(
        "Monthly Progress Report",
        "The contractual monthly submission to the client.",
        [
            "cover",
            "executive-summary",
            "milestones",
            "progress-vs-plan",
            "s-curve",
            "wbs-progress",
            "critical-path",
            "baseline-variance",
            "schedule-changes",
            "lookahead",
            "risk-top",
        ],
    ),
    _preset(
        "Executive Summary",
        "Two pages for upper management: where we are and where we land.",
        ["cover", "executive-summary", "progress-vs-plan", "s-curve", "milestones", "risk-top"],
    ),
    _preset(
        "Schedule Delay Analysis",
        "Support for an extension-of-time claim or a delay review.",
        [
            "cover",
            "executive-summary",
            "critical-path",
            "float-paths",
            "baseline-variance",
            "schedule-changes",
            "monte-carlo",
        ],
    ),
    _preset(
        "Schedule Quality Review",
        "Reviewing a submitted programme before accepting it.",
        ["cover", "dcma", "critical-path", "float-paths", "schedule-changes", "milestones"],
        orientation="landscape",
    ),
]


def _merge_with_catalogue(saved: list[dict]) -> list[ReportBlockConfig]:
    """Keep the saved blocks (order/enabled/options preserved), drop keys that
    are no longer in the catalogue, and append catalogue blocks the format has
    never seen as disabled entries so the builder can still offer them."""
    by_key = {b.get("key"): b for b in saved if b.get("key") in BLOCK_KEYS}
    merged = [
        ReportBlockConfig(
            key=b["key"],
            order=int(b.get("order", i)),
            enabled=bool(b.get("enabled", True)),
            options=b.get("options") or {},
        )
        for i, b in enumerate(by_key.values())
    ]
    next_order = max((b.order for b in merged), default=-1) + 1
    for key in BLOCK_KEYS:
        if key not in by_key:
            merged.append(
                ReportBlockConfig(key=key, order=next_order, enabled=False, options=dict(_DEFAULT_OPTIONS[key]))
            )
            next_order += 1
    merged.sort(key=lambda b: b.order)
    return merged


def _out(row: ReportFormat) -> ReportFormatOut:
    return ReportFormatOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        blocks=_merge_with_catalogue(list(row.blocks or [])),
        page_setup=row.page_setup or {"orientation": "portrait", "paper": "A4"},
        is_preset=row.is_preset,
        narrative=row.narrative,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _seed_presets(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    existing = {
        name
        for (name,) in db.query(ReportFormat.name).filter(
            ReportFormat.tenant_id == tenant_id, ReportFormat.project_id == project_id
        )
    }
    created = False
    for preset in PRESETS:
        if preset["name"] in existing:
            continue
        db.add(
            ReportFormat(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                project_id=project_id,
                name=preset["name"],
                description=preset["description"],
                blocks=preset["blocks"],
                page_setup=preset["page_setup"],
                is_preset=True,
                created_by_user_id=user_id,
            )
        )
        created = True
    if created:
        db.commit()


@router.get("/report-blocks", response_model=list[ReportBlockCatalogueOut])
def list_report_blocks(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[ReportBlockCatalogueOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    return BLOCK_CATALOGUE


@router.get("/report-formats", response_model=list[ReportFormatOut])
def list_report_formats(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[ReportFormatOut]:
    """Every saved format for this project. Seeds the four standard ones the
    first time a project is looked at, so a new project is never staring at an
    empty builder."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    _seed_presets(db, ctx.tenant_id, project_id, ctx.user.id)
    rows = (
        db.query(ReportFormat)
        .filter(ReportFormat.tenant_id == ctx.tenant_id, ReportFormat.project_id == project_id)
        .order_by(ReportFormat.is_preset.desc(), ReportFormat.name)
        .all()
    )
    return [_out(r) for r in rows]


@router.post("/report-formats", response_model=ReportFormatOut, status_code=status.HTTP_201_CREATED)
def create_report_format(
    project_id: uuid.UUID,
    payload: ReportFormatCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ReportFormatOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)

    name = payload.name.strip()
    clash = (
        db.query(ReportFormat)
        .filter(
            ReportFormat.tenant_id == ctx.tenant_id,
            ReportFormat.project_id == project_id,
            ReportFormat.name == name,
        )
        .first()
    )
    if clash is not None:
        raise HTTPException(status_code=400, detail=f'A format called "{name}" already exists')

    row = ReportFormat(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        name=name,
        description=payload.description,
        blocks=[b.model_dump() for b in payload.blocks],
        page_setup=payload.page_setup or {"orientation": "portrait", "paper": "A4"},
        is_preset=False,
        narrative=payload.narrative,
        created_by_user_id=ctx.user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


def _get_format(db: Session, project_id: uuid.UUID, format_id: uuid.UUID, ctx: AuthContext) -> ReportFormat:
    row = get_tenant_scoped_or_404(db, ReportFormat, format_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ReportFormat not found")
    return row


@router.get("/report-formats/{format_id}", response_model=ReportFormatOut)
def get_report_format(
    project_id: uuid.UUID,
    format_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ReportFormatOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    return _out(_get_format(db, project_id, format_id, ctx))


@router.patch("/report-formats/{format_id}", response_model=ReportFormatOut)
def update_report_format(
    project_id: uuid.UUID,
    format_id: uuid.UUID,
    payload: ReportFormatUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ReportFormatOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)
    row = _get_format(db, project_id, format_id, ctx)

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description
    if payload.blocks is not None:
        unknown = sorted({b.key for b in payload.blocks} - set(BLOCK_KEYS))
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown report block(s): {', '.join(unknown)}")
        row.blocks = [b.model_dump() for b in payload.blocks]
    if payload.page_setup is not None:
        row.page_setup = payload.page_setup
    if payload.narrative is not None:
        row.narrative = payload.narrative

    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/report-formats/{format_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_format(
    project_id: uuid.UUID,
    format_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> None:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)
    db.delete(_get_format(db, project_id, format_id, ctx))
    db.commit()


@router.get("/report-header", response_model=ReportHeaderOut)
def get_report_header(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ReportHeaderOut:
    """The provenance strip every report page carries. Kept in one endpoint so
    every block set states the same data date, revision and progress basis —
    a report whose pages disagree about its own data date gets rejected."""
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    current_import = get_current_import(db, ctx.tenant_id, project_id)
    baseline = (
        db.query(Baseline)
        .filter(
            Baseline.tenant_id == ctx.tenant_id,
            Baseline.project_id == project_id,
            Baseline.status == BaselineStatus.active,
        )
        .first()
    )
    # A baseline locked after the current programme was imported means the
    # comparison basis moved under the reader's feet since the last report.
    baseline_changed = bool(
        baseline is not None
        and current_import is not None
        and baseline.locked_at is not None
        and to_naive(baseline.locked_at) > to_naive(current_import.imported_at)
    )

    return ReportHeaderOut(
        project_id=project_id,
        project_name=project.name,
        project_code=project.code,
        data_date=to_naive(current_import.data_date) if current_import else None,
        schedule_revision=current_import.revision_label if current_import else None,
        schedule_filename=current_import.filename if current_import else None,
        imported_at=to_naive(current_import.imported_at) if current_import else None,
        baseline_label=baseline.version_label if baseline else None,
        baseline_changed_since=baseline_changed,
        progress_basis=PROGRESS_BASIS,
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        generated_by=ctx.user.full_name or ctx.user.email,
    )
