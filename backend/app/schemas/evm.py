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
    # Filled in by the route from schedule_imports.filename — the .xer this
    # baseline was locked from. Transient, not a mapped column.
    source_filename: str | None = None


class BaselineStatusOut(BaseModel):
    project_id: uuid.UUID
    has_active: bool
    active_baseline: BaselineOut | None
    all_baselines: list[BaselineOut]


class BaselineProgramResultOut(BaseModel):
    """Result of POST /projects/{id}/evm/baseline/program — one endpoint that
    creates the baseline on first upload and overwrites it in place on every
    later replacement."""

    mode: str  # "created" | "overwritten"
    filename: str
    activity_count: int
    critical_count: int
    warnings: list[str]
    baseline: BaselineOut


class BaselineResourceItemOut(BaseModel):
    rsrc_id: str
    name: str
    short_name: str | None
    rsrc_type: str
    unit_id: str | None
    budgeted_qty: float
    budgeted_cost: float
    assignment_count: int


class BaselineResourceSummaryOut(BaseModel):
    project_id: uuid.UUID
    baseline_id: uuid.UUID
    version_label: str
    resource_count: int
    labor_count: int
    material_count: int
    equipment_count: int
    total_budgeted_labor_hours: float
    total_budgeted_cost: float
    resources: list[BaselineResourceItemOut]


class BaselineVarianceHistogramBinOut(BaseModel):
    label: str
    count: int


class BaselineVarianceRowOut(BaseModel):
    activity_id: uuid.UUID
    external_id: str
    name: str
    wbs_code: str | None
    baseline_start: date | None
    baseline_finish: date | None
    current_start: date | None
    current_finish: date | None
    start_variance_days: int | None
    finish_variance_days: int | None
    is_critical: bool
    status: str
    percent_complete: int


class BaselineVarianceSummaryOut(BaseModel):
    activities_total: int
    ahead: int
    on_track: int
    behind: int
    baseline_finish: date | None
    forecast_finish: date | None
    project_finish_variance_days: int | None
    worst_slip_days: int | None
    critical_slip_count: int
    finish_variance_histogram: list[BaselineVarianceHistogramBinOut]


class BaselineVarianceOut(BaseModel):
    project_id: uuid.UUID
    baseline_id: uuid.UUID
    version_label: str
    summary: BaselineVarianceSummaryOut
    rows: list[BaselineVarianceRowOut]


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
