import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FloatPathActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    external_id: str
    name: str | None
    wbs_path: str | None
    status: str | None
    percent_complete: int
    early_start: date | None
    early_finish: date | None
    late_start: date | None
    late_finish: date | None
    total_float_days: float | None
    free_float_days: float | None
    is_critical: bool
    is_longest_path: bool
    # The relationship driving this activity from the one above it on the path.
    link_type: str | None
    lag_days: int | None
    link_gap_days: float | None


class FloatPathOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path_no: int
    total_float_days: float | None
    joins_at_external_id: str | None
    join_link_type: str | None
    join_lag_days: int | None
    join_gap_days: float | None
    activities: list[FloatPathActivityOut]


class FloatPathEndCandidateOut(BaseModel):
    """An activity worth offering as the end of a float path — milestones and
    the finish-side activities a planner actually analyses."""

    external_id: str
    name: str
    task_type: str | None
    early_finish: date | None
    total_float_days: float | None
    is_critical: bool


class FloatPathReportOut(BaseModel):
    project_id: uuid.UUID
    data_date: datetime | None
    revision_label: str | None
    end_activity_external_id: str
    end_activity_name: str | None
    method: Literal["total_float", "free_float"]
    requested_paths: int
    hours_per_day: float
    truncated: bool
    # How far path 1 can be pulled in before path 2 becomes the critical one.
    acceleration_headroom_days: float | None
    paths: list[FloatPathOut]
