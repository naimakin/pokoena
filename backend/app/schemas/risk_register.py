import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clamp_1_5(v: int | None) -> int | None:
    if v is None:
        return v
    return max(1, min(5, v))


class RiskItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    cause: str | None = Field(default=None, max_length=4000)
    effect: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=60)
    probability: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    status: Literal["open", "mitigating", "closed", "occurred"] = "open"
    owner_name: str | None = Field(default=None, max_length=255)
    wbs_path: str | None = Field(default=None, max_length=500)
    activity_external_ids: list[str] = Field(default_factory=list, max_length=200)


class RiskItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    cause: str | None = Field(default=None, max_length=4000)
    effect: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=60)
    probability: int | None = None
    impact: int | None = None
    status: Literal["open", "mitigating", "closed", "occurred"] | None = None
    owner_name: str | None = Field(default=None, max_length=255)
    wbs_path: str | None = Field(default=None, max_length=500)
    activity_external_ids: list[str] | None = Field(default=None, max_length=200)
    mitigation_strategy: Literal["mitigate", "avoid", "transfer", "accept"] | None = None
    mitigation_summary: str | None = Field(default=None, max_length=8000)

    @field_validator("probability", "impact")
    @classmethod
    def _clamp(cls, v: int | None) -> int | None:
        return _clamp_1_5(v)


class RiskActionCreate(BaseModel):
    action: str = Field(min_length=1, max_length=2000)
    owner_name: str | None = Field(default=None, max_length=255)
    target_date: date | None = None


class RiskActionUpdate(BaseModel):
    action: str | None = Field(default=None, min_length=1, max_length=2000)
    owner_name: str | None = Field(default=None, max_length=255)
    target_date: date | None = None
    status: Literal["open", "in_progress", "done", "dropped"] | None = None
    completed_at: date | None = None


class RiskActionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    risk_item_id: uuid.UUID
    order_index: int
    action: str
    owner_name: str | None
    target_date: date | None
    status: str
    completed_at: date | None


class RiskItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    title: str
    description: str | None
    cause: str | None
    effect: str | None
    category: str | None
    probability: int
    impact: int
    score: int
    status: str
    owner_name: str | None
    wbs_path: str | None
    activity_external_ids: list[str]
    mitigation_strategy: str | None
    mitigation_status: str
    mitigation_summary: str | None
    revision_no: int
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None
    review_note: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # transient
    action_item_count: int = 0
    created_by_name: str | None = None


class RiskItemDetailOut(RiskItemOut):
    items: list[RiskActionItemOut] = []


class ItemOrderIn(BaseModel):
    ordered_item_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class MitigationReviewIn(BaseModel):
    decision: Literal["accept", "needs_revision"]
    note: str | None = Field(default=None, max_length=2000)
