import uuid
from datetime import date

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
    # Populated by the route (transient, not a mapped column) so the UI can show
    # "FS ← MEP-2140" instead of a bare UUID.
    predecessor_external_id: str | None = None
    successor_external_id: str | None = None
