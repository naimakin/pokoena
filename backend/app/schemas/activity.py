import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.activity import ActivityStatus
from app.models.activity_relationship import LinkType


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    project_scope_id: uuid.UUID | None
    external_id: str
    name: str
    discipline: str
    planned_start: date | None
    planned_finish: date | None
    actual_start: date | None
    actual_finish: date | None
    percent_complete: int
    remaining_duration_days: int
    status: ActivityStatus

    # --- P6/CPM fields, populated by .xer import — None until a schedule has
    # been imported for this project. See services/xer_import.py. ---
    wbs_path: str | None = None
    task_type: str | None = None
    status_code: str | None = None
    target_duration_hours: float | None = None
    remaining_duration_hours: float | None = None
    early_start: date | None = None
    early_finish: date | None = None
    late_start: date | None = None
    late_finish: date | None = None
    total_float_hours: float | None = None
    free_float_hours: float | None = None
    is_critical: bool = False
    constraint_type: str | None = None
    constraint_date: date | None = None
    constraint_type_2: str | None = None
    constraint_date_2: date | None = None
    is_longest_path: bool = False


class ActivityUpdate(BaseModel):
    """Only the fields a subcontractor may edit directly, without admin review."""

    percent_complete: int | None = Field(default=None, ge=0, le=100)
    actual_start: date | None = None
    actual_finish: date | None = None
    remaining_duration_days: int | None = Field(default=None, ge=0)


class ActivityRelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    link_type: LinkType
    lag_days: int
    lag_hours: int | None = None
    # Populated by the route (transient, not a mapped column) so the UI can show
    # "FS ← MEP-2140" instead of a bare UUID.
    predecessor_external_id: str | None = None
    successor_external_id: str | None = None


class ScheduleImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    data_date: datetime | None
    imported_by_user_id: uuid.UUID
    imported_at: datetime
    activity_count: int
    critical_count: int
    warnings: list[str]
    revision_no: int | None = None
    revision_label: str | None = None
    roundtrip_from_export_id: uuid.UUID | None = None
