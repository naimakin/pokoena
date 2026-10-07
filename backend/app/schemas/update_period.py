import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.update_period import UpdatePeriodStatus


class UpdatePeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    period_number: int
    label: str
    opens_at: datetime
    deadline_at: datetime
    status: UpdatePeriodStatus
    closed_at: datetime | None = None


class UpdatePeriodCreate(BaseModel):
    """Opening a period: only the project and deadline are needed — the
    number is the next one, the label defaults to "Update <n>", and it opens now."""

    project_id: uuid.UUID
    deadline_at: datetime
    label: str | None = Field(default=None, max_length=120)
    period_number: int | None = None
    opens_at: datetime | None = None
