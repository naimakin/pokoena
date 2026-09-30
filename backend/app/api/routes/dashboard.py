import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_tenant_scoped_or_404, require_role
from app.engine.durations import activity_days
from app.models.activity import Activity, ActivityStatus
from app.models.baseline import Baseline, BaselineStatus
from app.models.change_request import ChangeRequest, ChangeRequestStatus
from app.models.dashboard_layout import DashboardLayout
from app.models.evm_snapshot import EvmSnapshot
from app.models.project import Project
from app.models.project_scope import ProjectScope
from app.models.risk_item import RiskItem, RiskStatus
from app.models.scope_submission import ScopeSubmission
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.update_period import UpdatePeriod
from app.models.user_tenant_role import TenantRole
from app.schemas.dashboard import (
    DashboardLayoutOut,
    DashboardLayoutUpdate,
    DashboardSummary,
    DashboardWidgetConfig,
    HealthFactor,
    ProjectHealth,
    RiskHighlight,
    ScopeSubmissionStatus,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ---------------------------------------------------------------------------
# Configurable dashboard: widget catalogue + server default layout
# ---------------------------------------------------------------------------

# Every widget the Dashboard page knows how to render. A saved layout may only
# reference keys in here (PUT /dashboard/layout 400s otherwise); the frontend
# registry (components/dashboard/DashboardWidgets.tsx) must stay in sync.
WIDGET_KEYS = (
    "update-period",
    "deadline",
    "scopes-submitted",
    "flagged",
    "health-badge",
    "s-curve",
    "risk-top3",
    "scope-table",
)

DEFAULT_WIDGETS: list[dict] = [
    {"key": key, "order": i, "enabled": True, "options": {}}
    for i, key in enumerate(WIDGET_KEYS)
]

VALID_THEME_KEYS = {"calm", "high-contrast", "mono-amber"}


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin, TenantRole.company_employee)),
) -> DashboardSummary:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)

    period = (
        db.query(UpdatePeriod)
        .filter(UpdatePeriod.tenant_id == ctx.tenant_id, UpdatePeriod.project_id == project_id)
        .order_by(UpdatePeriod.period_number.desc())
        .first()
    )

    # Orgs represented in this project: distinct subcontractor_org_id across the
    # project's scopes (a scope's org tag, not per-activity — see ProjectScope).
    orgs = (
        db.query(SubcontractorOrganization)
        .join(ProjectScope, ProjectScope.subcontractor_org_id == SubcontractorOrganization.id)
        .filter(ProjectScope.project_id == project_id, ProjectScope.tenant_id == ctx.tenant_id)
        .distinct()
        .all()
    )

    submitted_ids: set[uuid.UUID] = set()
    flagged_pending = 0
    if period:
        submitted_ids = {
            row.subcontractor_org_id
            for row in db.query(ScopeSubmission)
            .filter(ScopeSubmission.update_period_id == period.id)
            .all()
        }
        flagged_pending = (
            db.query(ChangeRequest)
            .filter(
                ChangeRequest.update_period_id == period.id,
                ChangeRequest.status == ChangeRequestStatus.pending,
            )
            .count()
        )

    scope_status = []
    for org in orgs:
        activities = (
            db.query(Activity)
            .join(ProjectScope, ProjectScope.id == Activity.project_scope_id)
            .filter(
                Activity.project_id == project_id,
                ProjectScope.subcontractor_org_id == org.id,
            )
            .all()
        )
        avg_pct = sum(a.percent_complete for a in activities) / len(activities) if activities else 0.0
        scope_status.append(
            ScopeSubmissionStatus(
                subcontractor_org_id=org.id,
                org_name=org.name,
                discipline=org.discipline,
                activity_count=len(activities),
                avg_percent_complete=round(avg_pct, 1),
                submitted=org.id in submitted_ids,
            )
        )

    return DashboardSummary(
        active_period_id=period.id if period else None,
        active_period_label=period.label if period else None,
        active_period_status=period.status.value if period else None,
        deadline_at=period.deadline_at if period else None,
        orgs_total=len(orgs),
        orgs_submitted=len(submitted_ids),
        flagged_pending=flagged_pending,
        scope_status=scope_status,
    )


# ---------------------------------------------------------------------------
# Widget layout: GET returns the saved arrangement or a server default;
# PUT upserts one row per (project, user).
# ---------------------------------------------------------------------------


def _merge_with_catalogue(saved: list[dict]) -> list[DashboardWidgetConfig]:
    """Keep the user's saved widgets (order/enabled/options preserved), drop
    any keys no longer in the catalogue, and append catalogue widgets the user
    has never seen as disabled entries so the configure modal can still show
    them."""
    by_key = {w.get("key"): w for w in saved if w.get("key") in WIDGET_KEYS}
    merged = [
        DashboardWidgetConfig(
            key=w["key"],
            order=int(w.get("order", i)),
            enabled=bool(w.get("enabled", True)),
            options=w.get("options") or {},
        )
        for i, w in enumerate(by_key.values())
    ]
    next_order = max((w.order for w in merged), default=-1) + 1
    for key in WIDGET_KEYS:
        if key not in by_key:
            merged.append(DashboardWidgetConfig(key=key, order=next_order, enabled=False))
            next_order += 1
    merged.sort(key=lambda w: w.order)
    return merged


@router.get("/layout", response_model=DashboardLayoutOut)
def get_dashboard_layout(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin, TenantRole.company_employee)),
) -> DashboardLayoutOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)

    row = (
        db.query(DashboardLayout)
        .filter(DashboardLayout.project_id == project_id, DashboardLayout.user_id == ctx.user.id)
        .first()
    )
    if row is None:
        return DashboardLayoutOut(
            project_id=project_id,
            user_id=ctx.user.id,
            theme_key="calm",
            widgets=[DashboardWidgetConfig(**w) for w in DEFAULT_WIDGETS],
            is_default=True,
        )

    theme_key = row.theme_key if row.theme_key in VALID_THEME_KEYS else "calm"
    return DashboardLayoutOut(
        project_id=project_id,
        user_id=ctx.user.id,
        theme_key=theme_key,
        widgets=_merge_with_catalogue(list(row.widgets or [])),
        is_default=False,
    )


@router.put("/layout", response_model=DashboardLayoutOut)
def put_dashboard_layout(
    payload: DashboardLayoutUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin, TenantRole.company_employee)),
) -> DashboardLayoutOut:
    get_tenant_scoped_or_404(db, Project, payload.project_id, ctx)

    unknown = sorted({w.key for w in payload.widgets} - set(WIDGET_KEYS))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown widget key(s): {', '.join(unknown)}")

    widgets_json = [w.model_dump() for w in payload.widgets]
    row = (
        db.query(DashboardLayout)
        .filter(DashboardLayout.project_id == payload.project_id, DashboardLayout.user_id == ctx.user.id)
        .first()
    )
    if row is None:
        row = DashboardLayout(
            id=uuid.uuid4(),
            tenant_id=ctx.tenant_id,
            project_id=payload.project_id,
            user_id=ctx.user.id,
            widgets=widgets_json,
            theme_key=payload.theme_key,
        )
        db.add(row)
    else:
        row.widgets = widgets_json
        row.theme_key = payload.theme_key
    db.commit()

    return DashboardLayoutOut(
        project_id=payload.project_id,
        user_id=ctx.user.id,
        theme_key=payload.theme_key,
        widgets=_merge_with_catalogue(widgets_json),
        is_default=False,
    )


# ---------------------------------------------------------------------------
# Derived widgets: project health composite + risk highlights.
# The health composite is heuristics over data on hand (scope submissions, EVM
# snapshots, CPM float). Risk highlights blend those heuristics with the real
# Risk Register (models/risk_item.py) — high-score open risks rank first.
# ---------------------------------------------------------------------------

_STATUS_SCORE = {"good": 100, "warn": 60, "crit": 20}


def _gather_signals(db: Session, ctx: AuthContext, project_id: uuid.UUID) -> dict:
    activities = (
        db.query(Activity)
        .filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id)
        .all()
    )

    period = (
        db.query(UpdatePeriod)
        .filter(UpdatePeriod.tenant_id == ctx.tenant_id, UpdatePeriod.project_id == project_id)
        .order_by(UpdatePeriod.period_number.desc())
        .first()
    )
    orgs_total = (
        db.query(ProjectScope.subcontractor_org_id)
        .filter(
            ProjectScope.project_id == project_id,
            ProjectScope.tenant_id == ctx.tenant_id,
            ProjectScope.subcontractor_org_id.isnot(None),
        )
        .distinct()
        .count()
    )
    orgs_submitted = 0
    flagged_pending = 0
    if period:
        orgs_submitted = (
            db.query(ScopeSubmission.subcontractor_org_id)
            .filter(ScopeSubmission.update_period_id == period.id)
            .distinct()
            .count()
        )
        flagged_pending = (
            db.query(ChangeRequest)
            .filter(
                ChangeRequest.update_period_id == period.id,
                ChangeRequest.status == ChangeRequestStatus.pending,
            )
            .count()
        )

    baseline = (
        db.query(Baseline)
        .filter(
            Baseline.tenant_id == ctx.tenant_id,
            Baseline.project_id == project_id,
            Baseline.status == BaselineStatus.active,
        )
        .first()
    )
    latest_snapshot = None
    if baseline is not None:
        latest_snapshot = (
            db.query(EvmSnapshot)
            .filter(EvmSnapshot.project_id == project_id, EvmSnapshot.baseline_id == baseline.id)
            .order_by(EvmSnapshot.snapshot_date.desc())
            .first()
        )

    return {
        "activities": activities,
        "period": period,
        "orgs_total": orgs_total,
        "orgs_submitted": orgs_submitted,
        "flagged_pending": flagged_pending,
        "baseline": baseline,
        "latest_snapshot": latest_snapshot,
        "today": datetime.now(timezone.utc).date(),
    }


def _index_status(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 0.95:
        return "good"
    if value >= 0.85:
        return "warn"
    return "crit"


def _overdue_activities(activities: list[Activity], today: date) -> list[Activity]:
    return [
        a
        for a in activities
        if a.status != ActivityStatus.complete and a.planned_finish is not None and a.planned_finish < today
    ]


def _negative_float_activities(activities: list[Activity]) -> list[Activity]:
    return [a for a in activities if a.total_float_hours is not None and a.total_float_hours < 0]


@router.get("/health", response_model=ProjectHealth)
def get_project_health(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin, TenantRole.company_employee)),
) -> ProjectHealth:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    s = _gather_signals(db, ctx, project_id)
    activities: list[Activity] = s["activities"]
    factors: list[HealthFactor] = []

    # 1. Scope submissions for the latest period.
    if s["period"] and s["orgs_total"] > 0:
        rate = s["orgs_submitted"] / s["orgs_total"]
        status = "good" if rate >= 0.9 else "warn" if rate >= 0.5 else "crit"
        factors.append(
            HealthFactor(
                key="scope_submissions", label="Scope submissions",
                status=status,
                detail=f"{s['orgs_submitted']} of {s['orgs_total']} scopes submitted this period",
            )
        )
    else:
        factors.append(
            HealthFactor(key="scope_submissions", label="Scope submissions", status="unknown", detail="No open update period with subcontractor scopes")
        )

    # 2 & 3. EVM schedule + cost performance.
    snap = s["latest_snapshot"]
    if snap is not None:
        factors.append(
            HealthFactor(
                key="evm", label="Schedule performance (SPI)",
                status=_index_status(snap.spi),
                detail=f"SPI {snap.spi:.2f}" if snap.spi is not None else "Not enough progress data",
            )
        )
        factors.append(
            HealthFactor(
                key="evm", label="Cost performance (CPI)",
                status=_index_status(snap.cpi),
                detail=f"CPI {snap.cpi:.2f}" if snap.cpi is not None else "Not enough progress data",
            )
        )
    elif s["baseline"] is not None:
        factors.append(HealthFactor(key="evm", label="EVM performance", status="unknown", detail="Baseline locked, no progress submitted yet"))
    else:
        factors.append(HealthFactor(key="evm", label="EVM performance", status="unknown", detail="No baseline locked"))

    # 4. Critical path float.
    if any(a.total_float_hours is not None for a in activities):
        negative = _negative_float_activities(activities)
        if negative:
            factors.append(
                HealthFactor(
                    key="critical_path", label="Critical path",
                    status="crit",
                    detail=f"{len(negative)} activit{'y' if len(negative) == 1 else 'ies'} with negative float",
                )
            )
        else:
            factors.append(HealthFactor(key="critical_path", label="Critical path", status="good", detail="No negative float on the network"))
    else:
        factors.append(HealthFactor(key="critical_path", label="Critical path", status="unknown", detail="No schedule imported"))

    # 5. Pending change reviews — only a meaningful signal once a period exists
    # to flag changes against; otherwise "0 pending" isn't really good news.
    pending = s["flagged_pending"]
    if s["period"]:
        factors.append(
            HealthFactor(
                key="pending_reviews", label="Pending reviews",
                status="good" if pending == 0 else "warn" if pending < 5 else "crit",
                detail=f"{pending} change request{'' if pending == 1 else 's'} awaiting a decision",
            )
        )
    else:
        factors.append(HealthFactor(key="pending_reviews", label="Pending reviews", status="unknown", detail="No update period opened yet"))

    # 6. Overdue activities.
    if activities:
        overdue = _overdue_activities(activities, s["today"])
        factors.append(
            HealthFactor(
                key="overdue", label="Overdue activities",
                status="good" if not overdue else "warn" if len(overdue) <= 5 else "crit",
                detail=f"{len(overdue)} activit{'y' if len(overdue) == 1 else 'ies'} past planned finish",
            )
        )
    else:
        factors.append(HealthFactor(key="overdue", label="Overdue activities", status="unknown", detail="No activities yet"))

    scored = [_STATUS_SCORE[f.status] for f in factors if f.status in _STATUS_SCORE]
    if not scored:
        return ProjectHealth(score=None, grade="—", status="unknown", factors=factors)

    score = round(sum(scored) / len(scored))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "E"
    status = "good" if score >= 75 else "warn" if score >= 50 else "crit"
    return ProjectHealth(score=score, grade=grade, status=status, factors=factors)


@router.get("/risk-highlights", response_model=list[RiskHighlight])
def get_risk_highlights(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin, TenantRole.company_employee)),
) -> list[RiskHighlight]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    s = _gather_signals(db, ctx, project_id)
    activities: list[Activity] = s["activities"]
    _SEV_RANK = {"high": 0, "medium": 1, "low": 2}
    candidates: list[tuple[float, RiskHighlight]] = []

    # Risk register — high-score open/mitigating risks outrank the heuristics.
    register_risks = (
        db.query(RiskItem)
        .filter(
            RiskItem.tenant_id == ctx.tenant_id,
            RiskItem.project_id == project_id,
            RiskItem.status.in_([RiskStatus.open, RiskStatus.mitigating]),
            RiskItem.score >= 12,
        )
        .order_by(RiskItem.score.desc())
        .limit(3)
        .all()
    )
    for r in register_risks:
        candidates.append(
            (
                r.score * 40,
                RiskHighlight(
                    title=f"{r.code} {r.title}",
                    detail=f"P{r.probability}×I{r.impact} (score {r.score}) · {r.status.value}",
                    severity="high" if r.score >= 15 else "medium",
                    source="Risk register",
                ),
            )
        )

    # Negative float on the critical path — the sharpest schedule signal.
    for a in sorted(_negative_float_activities(activities), key=lambda x: activity_days(x, x.total_float_hours or 0))[:5]:
        days = abs(round(activity_days(a, a.total_float_hours or 0), 1))
        candidates.append(
            (
                1000 + days,
                RiskHighlight(
                    title=f"Negative float — {a.external_id}",
                    detail=f"{a.name}: {days}d behind on the critical path",
                    severity="high",
                    source="Critical path",
                ),
            )
        )

    # Overdue activities.
    overdue = _overdue_activities(activities, s["today"])
    if overdue:
        worst = max(overdue, key=lambda a: (s["today"] - a.planned_finish).days)
        slip = (s["today"] - worst.planned_finish).days
        candidates.append(
            (
                500 + slip,
                RiskHighlight(
                    title=f"{len(overdue)} overdue activit{'y' if len(overdue) == 1 else 'ies'}",
                    detail=f"Worst: {worst.external_id} {worst.name} — {slip}d past planned finish",
                    severity="high" if slip > 14 or len(overdue) > 5 else "medium",
                    source="Progress",
                ),
            )
        )

    # Scope submission shortfall against the current period.
    if s["period"] and s["orgs_total"] > 0:
        missing = s["orgs_total"] - s["orgs_submitted"]
        if missing > 0:
            rate = s["orgs_submitted"] / s["orgs_total"]
            candidates.append(
                (
                    300 + missing,
                    RiskHighlight(
                        title=f"{missing} scope{'' if missing == 1 else 's'} not submitted",
                        detail=f"{s['period'].label}: {round(rate * 100)}% of scopes reported so far",
                        severity="high" if rate < 0.5 else "medium",
                        source="Update period",
                    ),
                )
            )

    # Flagged-change backlog.
    if s["flagged_pending"] >= 3:
        candidates.append(
            (
                200 + s["flagged_pending"],
                RiskHighlight(
                    title=f"{s['flagged_pending']} changes awaiting review",
                    detail="Unreviewed logic/date changes can mask schedule slippage",
                    severity="medium" if s["flagged_pending"] < 10 else "high",
                    source="Review queue",
                ),
            )
        )

    # No baseline locked while a period is open — EVM is blind.
    if s["baseline"] is None and activities:
        candidates.append(
            (
                100.0,
                RiskHighlight(
                    title="No baseline locked",
                    detail="Lock a Performance Measurement Baseline to track SPI/CPI and forecast completion",
                    severity="low",
                    source="EVM",
                ),
            )
        )

    candidates.sort(key=lambda c: (_SEV_RANK[c[1].severity], -c[0]))
    return [rh for _, rh in candidates[:3]]
