import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScopeSubmissionStatus(BaseModel):
    subcontractor_org_id: uuid.UUID
    org_name: str
    discipline: str
    activity_count: int
    avg_percent_complete: float
    submitted: bool


class CurrentUpdateOut(BaseModel):
    """The latest schedule update (Program Library's current import) — what the
    period cards fall back to when no subcontractor update period is running.
    `*_this_update` counts actual starts/finishes between the previous update's
    data date and this one's (None on the first update)."""

    revision_label: str | None
    filename: str
    data_date: date
    imported_at: datetime
    previous_label: str | None
    previous_data_date: date | None
    cadence_days: int | None
    next_data_date: date | None
    activities_total: int
    activities_complete: int
    activities_in_progress: int
    started_this_update: int | None
    finished_this_update: int | None
    # Against the locked baseline (None without one) — services/progress_summary.py.
    planned_pct: float | None = None
    actual_pct: float | None = None
    spi: float | None = None


class DashboardSummary(BaseModel):
    active_period_id: uuid.UUID | None
    active_period_label: str | None
    active_period_status: str | None
    deadline_at: datetime | None
    orgs_total: int
    orgs_submitted: int
    # Recovery plans for slipped activities (services/mitigation.py): how many
    # the latest update calls for, and how many of those are acknowledged.
    recovery_required: int = 0
    recovery_acknowledged: int = 0
    current_update: CurrentUpdateOut | None = None
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
    # Stable id the frontend maps to a detail page (labels are display copy and may change).
    key: str
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


# ---------------------------------------------------------------------------
# Analytics: hours and cost, budget vs planned vs actual (services/analytics.py)
# ---------------------------------------------------------------------------


class MeasureOut(BaseModel):
    """Labor hours or cost. `budget` is the locked baseline's, `current_budget`
    the current programme's; `planned` is the baseline spread to the data date."""

    budget: float
    current_budget: float
    planned: float
    actual: float
    remaining: float

    @classmethod
    def of(cls, m) -> "MeasureOut":
        """From a services.analytics.Measure, rounded for the wire."""
        return cls(
            budget=round(m.budget, 2),
            current_budget=round(m.current_budget, 2),
            planned=round(m.planned, 2),
            actual=round(m.actual, 2),
            remaining=round(m.remaining, 2),
        )


class AnalyticsMonthOut(BaseModel):
    month: str  # "YYYY-MM"
    planned_hours: float
    actual_hours: float
    planned_cost: float
    actual_cost: float


class AnalyticsGroupOut(BaseModel):
    label: str
    hours: MeasureOut
    cost: MeasureOut


class AnalyticsGroupingOut(BaseModel):
    key: str  # "wbs:2", "code:<uuid>"
    label: str
    groups: list[AnalyticsGroupOut]


class BehindActivityOut(BaseModel):
    activity_id: uuid.UUID
    external_id: str
    name: str
    wbs_name: str | None
    planned_pct: float
    actual_pct: float
    variance: float
    baseline_finish: date | None


class ProjectAnalyticsOut(BaseModel):
    data_date: date
    currency: str
    baseline_label: str
    baseline_start: date | None
    baseline_finish: date | None
    forecast_finish: date | None
    finish_variance_days: int | None
    planned_pct: float | None
    actual_pct: float | None
    spi: float | None
    elapsed_pct: float | None
    hours: MeasureOut
    # None when the programme carries no cost at all.
    cost: MeasureOut | None
    months: list[AnalyticsMonthOut]
    groupings: list[AnalyticsGroupingOut]
    behind_total: int
    behind: list[BehindActivityOut]
