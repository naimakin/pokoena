import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.change_request import ChangeRequestStatus, RiskLevel


class ChangeRequestCreate(BaseModel):
    update_period_id: uuid.UUID
    activity_relationship_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None
    field_changed: str
    before_value: str
    after_value: str
    justification: str
    risk_level: RiskLevel = RiskLevel.medium


class ChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    update_period_id: uuid.UUID
    activity_id: uuid.UUID | None
    activity_relationship_id: uuid.UUID | None
    requested_by_user_id: uuid.UUID
    field_changed: str
    before_value: str
    after_value: str
    justification: str
    risk_level: RiskLevel
    status: ChangeRequestStatus
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime

    # Populated by list_change_requests() for display; absent (falls back to None)
    # on the create/approve/reject responses, which return the bare ORM row.
    requested_by_name: str | None = None
    requested_by_company: str | None = None
    activity_name: str | None = None
    activity_external_id: str | None = None


class BulkApproveRequest(BaseModel):
    ids: list[uuid.UUID]
