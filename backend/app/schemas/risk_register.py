import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    # --- QSRA quantification ---
    qsra_enabled: bool | None = None
    risk_kind: Literal["threat", "opportunity"] | None = None
    probability_pct: float | None = Field(default=None, ge=0, le=100)
    impact_mode: Literal["duration_pct", "delay_days"] | None = None
    impact_min: float | None = Field(default=None, ge=0, le=100000)
    impact_ml: float | None = Field(default=None, ge=0, le=100000)
    impact_max: float | None = Field(default=None, ge=0, le=100000)
    impact_distribution: Literal["triangular", "pert", "uniform"] | None = None
    post_probability_pct: float | None = Field(default=None, ge=0, le=100)
    post_impact_min: float | None = Field(default=None, ge=0, le=100000)
    post_impact_ml: float | None = Field(default=None, ge=0, le=100000)
    post_impact_max: float | None = Field(default=None, ge=0, le=100000)
    impact_in_schedule: bool | None = None
    apply_to_wbs: bool | None = None

    @model_validator(mode="after")
    def _ordered_ranges(self):
        for prefix in ("impact", "post_impact"):
            lo, ml, hi = (getattr(self, f"{prefix}_{k}") for k in ("min", "ml", "max"))
            present = [v for v in (lo, ml, hi) if v is not None]
            if len(present) >= 2 and present != sorted(present):
                raise ValueError(f"{prefix.replace('_', ' ')} must satisfy min ≤ most likely ≤ max")
        return self


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

    # --- QSRA quantification ---
    qsra_enabled: bool | None = None
    risk_kind: Literal["threat", "opportunity"] | None = None
    probability_pct: float | None = Field(default=None, ge=0, le=100)
    impact_mode: Literal["duration_pct", "delay_days"] | None = None
    impact_min: float | None = Field(default=None, ge=0, le=100000)
    impact_ml: float | None = Field(default=None, ge=0, le=100000)
    impact_max: float | None = Field(default=None, ge=0, le=100000)
    impact_distribution: Literal["triangular", "pert", "uniform"] | None = None
    post_probability_pct: float | None = Field(default=None, ge=0, le=100)
    post_impact_min: float | None = Field(default=None, ge=0, le=100000)
    post_impact_ml: float | None = Field(default=None, ge=0, le=100000)
    post_impact_max: float | None = Field(default=None, ge=0, le=100000)
    impact_in_schedule: bool | None = None
    apply_to_wbs: bool | None = None

    @model_validator(mode="after")
    def _ordered_ranges(self):
        for prefix in ("impact", "post_impact"):
            lo, ml, hi = (getattr(self, f"{prefix}_{k}") for k in ("min", "ml", "max"))
            present = [v for v in (lo, ml, hi) if v is not None]
            if len(present) >= 2 and present != sorted(present):
                raise ValueError(f"{prefix.replace('_', ' ')} must satisfy min ≤ most likely ≤ max")
        return self

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
    qsra_enabled: bool = False
    risk_kind: str = "threat"
    probability_pct: float | None = None
    impact_mode: str = "duration_pct"
    impact_min: float | None = None
    impact_ml: float | None = None
    impact_max: float | None = None
    impact_distribution: str = "triangular"
    post_probability_pct: float | None = None
    post_impact_min: float | None = None
    post_impact_ml: float | None = None
    post_impact_max: float | None = None
    impact_in_schedule: bool = False
    apply_to_wbs: bool = False
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
