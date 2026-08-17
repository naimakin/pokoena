import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ActivityRiskOverrideIn(BaseModel):
    activity_id: uuid.UUID
    optimistic: float = Field(ge=0)
    most_likely: float = Field(ge=0)
    pessimistic: float = Field(ge=0)


class MonteCarloRequest(BaseModel):
    iterations: int = Field(default=1000, ge=1, le=5000)
    spread: float = Field(default=0.20, ge=0, le=1)
    overrides: list[ActivityRiskOverrideIn] = Field(default_factory=list)


class MonteCarloHistogramBinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str
    count: int
    cumulative_pct: float


class MonteCarloResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    iterations: int
    project_finish_p10: datetime
    project_finish_p50: datetime
    project_finish_p80: datetime
    project_finish_p90: datetime
    mean_finish: datetime
    histogram: list[MonteCarloHistogramBinOut]
    critical_activities: list[str]
