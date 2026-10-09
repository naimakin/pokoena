import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.dashboard import MeasureOut


class PortfolioMonthOut(BaseModel):
    month: str  # "YYYY-MM"
    score: int  # sum of the Criticality Scores of the activities active that month
    tasks: int
    critical: int  # unfinished, total float <= 0
    delay_drivers: int  # unfinished, negative total float


class PortfolioProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    has_schedule: bool
    data_date: datetime | None = None
    activity_count: int = 0
    spi: float | None = None
    planned_pct: float | None = None
    actual_pct: float | None = None
    start: date | None = None
    actual_start: date | None = None
    forecast_finish: date | None = None
    baseline_finish: date | None = None
    finish_variance_days: int | None = None
    quality_score: float | None = None
    # "ahead" | "on_schedule" | "slightly_behind" | "behind" | "no_data"
    progress: str = "no_data"
    risk: str = "LOW"  # LOW | MEDIUM | HIGH
    quality: str = "LOW"  # HIGH | MEDIUM | LOW
    critical_count: int = 0
    negative_float_count: int = 0
    months: list[PortfolioMonthOut] = []
    has_baseline: bool = False
    hours: MeasureOut | None = None
    cost: MeasureOut | None = None


class PortfolioActivityOut(BaseModel):
    project_id: uuid.UUID
    project_code: str
    id: uuid.UUID
    external_id: str
    name: str
    status: str
    task_type: str | None = None
    start: date | None = None
    finish: date | None = None
    total_float_days: float | None = None
    criticality_score: int | None = None
    criticality_breakdown: dict[str, int] | None = None


class PortfolioSummaryOut(BaseModel):
    progress: dict[str, int]  # bucket -> project count
    behind_avg_overrun_pct: float | None = None
    risk: dict[str, int]
    quality: dict[str, int]


class PortfolioOut(BaseModel):
    generated_at: datetime
    projects: list[PortfolioProjectOut]
    months: list[PortfolioMonthOut]  # the portfolio row: every project summed
    summary: PortfolioSummaryOut
    top_activities: list[PortfolioActivityOut]
    currency: str = "EUR"


class PortfolioMonthActivitiesOut(BaseModel):
    project_id: uuid.UUID
    month: str
    total: int
    activities: list[PortfolioActivityOut]
