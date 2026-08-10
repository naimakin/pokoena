import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
    project_id: uuid.UUID
    period_number: int
    label: str
    opens_at: datetime
    deadline_at: datetime
