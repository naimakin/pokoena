import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class StatusTrendPointOut(BaseModel):
    label: str
    value: float


class StatusCardOut(BaseModel):
    verdict: str
    headline: str
    metric: float | None
    delta: float | None
    series: list[StatusTrendPointOut]


class StatusSummaryOut(BaseModel):
    progress: StatusCardOut
    risk: StatusCardOut
    quality: StatusCardOut


class PriorityQuadrantOut(BaseModel):
    key: str
    label: str
    program_count: int
    user_count: int
    recommendation_count: int


class PriorityActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: uuid.UUID
    external_id: str
    name: str
    discipline: str
    planned_start: date | None
    planned_finish: date | None
    total_float_days: float | None
    percent_complete: int
    is_critical: bool
    is_overdue: bool
    is_delay_driver: bool


class PrioritiesOut(BaseModel):
    quadrants: list[PriorityQuadrantOut]
    activities: dict[str, list[PriorityActivityOut]]
    filtered_total: int


class ProjectStatusOut(BaseModel):
    project_id: uuid.UUID
    data_date: datetime | None
    latest_revision_label: str | None
    latest_filename: str | None
    imported_at: datetime | None
    has_snapshots: bool
    summary: StatusSummaryOut
    priorities: PrioritiesOut
