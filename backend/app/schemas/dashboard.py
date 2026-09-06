import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScopeSubmissionStatus(BaseModel):
    subcontractor_org_id: uuid.UUID
    org_name: str
    discipline: str
    activity_count: int
    avg_percent_complete: float
    submitted: bool


class DashboardSummary(BaseModel):
    active_period_id: uuid.UUID | None
    active_period_label: str | None
    active_period_status: str | None
    deadline_at: datetime | None
    orgs_total: int
    orgs_submitted: int
    flagged_pending: int
    scope_status: list[ScopeSubmissionStatus]


# ---------------------------------------------------------------------------
# Configurable dashboard: per-user widget layout + colour theme
# ---------------------------------------------------------------------------

DashboardThemeKey = Literal["calm", "high-contrast", "mono-amber"]


class DashboardWidgetConfig(BaseModel):
    key: str
    order: int
    enabled: bool = True
    options: dict = Field(default_factory=dict)


class DashboardLayoutOut(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    theme_key: DashboardThemeKey
    widgets: list[DashboardWidgetConfig]
    # True when no saved row exists yet and this is the server default — the
    # frontend uses it to open the configure modal on first visit.
    is_default: bool


class DashboardLayoutUpdate(BaseModel):
    project_id: uuid.UUID
    theme_key: DashboardThemeKey
    widgets: list[DashboardWidgetConfig]


# ---------------------------------------------------------------------------
# Project health + risk highlights (derived, read-only widgets)
# ---------------------------------------------------------------------------

HealthStatus = Literal["good", "warn", "crit", "unknown"]


class HealthFactor(BaseModel):
    label: str
    status: HealthStatus
    detail: str


class ProjectHealth(BaseModel):
    # 0-100 composite, or None when there's not enough data to score anything.
    score: int | None
    grade: str
    status: HealthStatus
    factors: list[HealthFactor]


class RiskHighlight(BaseModel):
    title: str
    detail: str
    severity: Literal["low", "medium", "high"]
    source: str
