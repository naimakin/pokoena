import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_tenant_scoped_or_404, require_role
from app.models.activity import Activity
from app.models.change_request import ChangeRequest, ChangeRequestStatus
from app.models.project import Project
from app.models.project_scope import ProjectScope
from app.models.scope_submission import ScopeSubmission
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.update_period import UpdatePeriod
from app.models.user_tenant_role import TenantRole
from app.schemas.dashboard import DashboardSummary, ScopeSubmissionStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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
