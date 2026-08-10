import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_roles
from app.models.activity import Activity
from app.models.change_request import ChangeRequest, ChangeRequestStatus
from app.models.company import Company
from app.models.scope_submission import ScopeSubmission
from app.models.update_period import UpdatePeriod
from app.schemas.dashboard import DashboardSummary, ScopeSubmissionStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    project_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(require_roles("admin", "viewer"))
) -> DashboardSummary:
    period = (
        db.query(UpdatePeriod)
        .filter(UpdatePeriod.project_id == project_id)
        .order_by(UpdatePeriod.period_number.desc())
        .first()
    )

    companies = (
        db.query(Company)
        .join(Activity, Activity.company_id == Company.id)
        .filter(Activity.project_id == project_id)
        .distinct()
        .all()
    )

    submitted_ids: set[uuid.UUID] = set()
    flagged_pending = 0
    if period:
        submitted_ids = {
            row.company_id
            for row in db.query(ScopeSubmission).filter(ScopeSubmission.update_period_id == period.id).all()
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
    for company in companies:
        activities = (
            db.query(Activity)
            .filter(Activity.project_id == project_id, Activity.company_id == company.id)
            .all()
        )
        avg_pct = sum(a.percent_complete for a in activities) / len(activities) if activities else 0.0
        scope_status.append(
            ScopeSubmissionStatus(
                company_id=company.id,
                company_name=company.name,
                discipline=company.discipline,
                activity_count=len(activities),
                avg_percent_complete=round(avg_pct, 1),
                submitted=company.id in submitted_ids,
            )
        )

    return DashboardSummary(
        active_period_id=period.id if period else None,
        active_period_label=period.label if period else None,
        active_period_status=period.status.value if period else None,
        deadline_at=period.deadline_at if period else None,
        companies_total=len(companies),
        companies_submitted=len(submitted_ids),
        flagged_pending=flagged_pending,
        scope_status=scope_status,
    )
