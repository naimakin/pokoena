import uuid
from datetime import datetime

from pydantic import BaseModel


class ScopeSubmissionStatus(BaseModel):
    company_id: uuid.UUID
    company_name: str
    discipline: str
    activity_count: int
    avg_percent_complete: float
    submitted: bool


class DashboardSummary(BaseModel):
    active_period_id: uuid.UUID | None
    active_period_label: str | None
    active_period_status: str | None
    deadline_at: datetime | None
    companies_total: int
    companies_submitted: int
    flagged_pending: int
    scope_status: list[ScopeSubmissionStatus]
