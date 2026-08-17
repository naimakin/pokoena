import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ActivityEvmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: uuid.UUID
    external_id: str
    name: str
    status_code: str | None
    percent_complete: int

    bac: float
    pv: float | None
    ev: float
    ac: float

    cpi: float | None
    spi: float | None
    sv: float | None
    cv: float

    eac_cpi: float | None
    eac_pf: float | None
    vac: float | None

    remaining_manhour: float
    remaining_qty: float


class QuickEvmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data_date: datetime | None

    bac: float
    pv: float | None
    ev: float
    ac: float

    cpi: float | None
    spi: float | None
    sv: float | None
    cv: float

    eac_cpi: float | None
    eac_pf: float | None
    vac: float | None

    activity_results: list[ActivityEvmOut]


# --- Phase B: baseline lock + S-curve time series ---------------------------


class BaselineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    schedule_import_id: uuid.UUID
    version_label: str
    locked_at: datetime | None
    locked_by_user_id: uuid.UUID | None
    total_budget_manhours: float
    target_start_date: date
    target_end_date: date
    distribution_method: str
    status: str
    activity_count: int
    notes: str | None
    created_at: datetime


class BaselineStatusOut(BaseModel):
    project_id: uuid.UUID
    has_active: bool
    active_baseline: BaselineOut | None
    all_baselines: list[BaselineOut]


class LockBaselineRequest(BaseModel):
    version_label: str = Field(default="Target-1", max_length=120)
    notes: str | None = Field(default=None, max_length=500)


class LockBaselineResultOut(BaseModel):
    status: str
    baseline_id: uuid.UUID
    version_label: str
    bac: float
    activity_count: int
    target_start: date
    target_end: date


class ProgressEntryIn(BaseModel):
    activity_id: uuid.UUID
    entry_date: date
    burned_manhours_daily: float = Field(ge=0)
    physical_pct_snapshot: float | None = Field(default=None, ge=0, le=100)
    crew_size: int | None = None
    notes: str | None = Field(default=None, max_length=500)


class ProgressBatchIn(BaseModel):
    entries: list[ProgressEntryIn] = Field(min_length=1, max_length=500)


class ProgressSubmitResultOut(BaseModel):
    status: str
    written: int
    out_of_sequence_count: int


class ProgressEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_id: uuid.UUID
    entry_date: date
    burned_manhours_daily: float
    physical_pct_snapshot: float | None
    entry_type: str
    crew_size: int | None
    notes: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    is_out_of_sequence: bool


class EvmScurvePointOut(BaseModel):
    date: str
    pv: float
    ev: float
    ac: float
    bac: float
    spi: float | None
    cpi: float | None
    sv: float
    cv: float
    eac: float | None
    etc: float | None
    tcpi: float | None
    pct_planned: float
    pct_earned: float
    tcpi_critical: bool


class EvmScurveOut(BaseModel):
    project_id: uuid.UUID
    baseline_id: uuid.UUID
    version_label: str
    bac: float
    granularity: str
    points: int
    series: list[EvmScurvePointOut]


class EvmSummaryOut(BaseModel):
    project_id: uuid.UUID
    baseline_id: uuid.UUID | None
    version_label: str | None
    status: str
    message: str | None = None
    as_of_date: date | None = None
    bac: float
    pv_cumulative: float
    ev_cumulative: float
    ac_cumulative: float
    spi: float | None
    cpi: float | None
    sv: float
    cv: float
    eac: float | None
    etc: float | None
    tcpi: float | None
    tcpi_critical: bool
    pct_planned: float
    pct_earned: float
    total_ac_raw: float
    entry_count: int
