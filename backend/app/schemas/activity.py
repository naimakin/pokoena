import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.engine.durations import DEFAULT_HOURS_PER_DAY, valid_hours_per_day
from app.models.activity import ActivityStatus
from app.models.activity_relationship import LinkType


SiteRisk = Literal["high", "standard", "low"]


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
    # P6's TASK.phys_complete_pct; `percent_complete` above is the % shown
    # (services/activity_progress.py::display_percent).
    phys_complete_pct: float | None = None
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
    # The activity's own calendar day length (CALENDAR.day_hr_cnt): every
    # *_hours field above shows in days as hours / hours_per_day — see
    # engine/durations.py. Never a flat 8 unless the activity has no calendar.
    hours_per_day: float = DEFAULT_HOURS_PER_DAY

    @field_validator("hours_per_day", mode="before")
    @classmethod
    def _calendar_or_default(cls, v: float | None) -> float:
        return valid_hours_per_day(v)

    # --- Poko's own annotations (see models/activity.py) ---
    is_important: bool = False
    tags: list[str] = []
    notes: str | None = None
    site_risk: SiteRisk | None = None

    # --- Criticality Score (services/criticality.py), computed on read; None
    # for completed work and on rows that don't carry it (import snapshots). ---
    criticality_score: int | None = None
    criticality_breakdown: dict[str, int] | None = None


class ActivityUpdate(BaseModel):
    """What the Activity modal may write: the progress fields a subcontractor
    owns, plus Poko's own annotations. Everything else on an activity comes from
    the .xer and is read-only here."""

    percent_complete: int | None = Field(default=None, ge=0, le=100)
    actual_start: date | None = None
    actual_finish: date | None = None
    remaining_duration_days: int | None = Field(default=None, ge=0)
    is_important: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)
    # Site / supply risk for the Criticality Score; null clears it (scored as
    # standard).
    site_risk: SiteRisk | None = None


class ActivityBatchItemIn(ActivityUpdate):
    """One row of a PATCH /activities?project_id= batch — the editable fields
    plus which activity they apply to."""

    id: uuid.UUID


class ActivityBatchUpdateIn(BaseModel):
    updates: list[ActivityBatchItemIn] = Field(min_length=1, max_length=2000)


class ActivityBatchRowError(BaseModel):
    id: uuid.UUID
    error: str


class ActivityBatchResultOut(BaseModel):
    saved: list[ActivityOut]
    failed: list[ActivityBatchRowError]


class ActivityAssignmentOut(BaseModel):
    """One TASKRSRC row of an activity, as Poko holds it: budgeted / actual /
    remaining units. All three follow the activity's % for every resource
    type (services/activity_progress.py)."""

    id: uuid.UUID
    rsrc_id: str
    name: str
    short_name: str | None = None
    rsrc_type: str
    unit_id: str | None = None
    target_qty: float
    act_reg_qty: float
    remain_qty: float


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


class ActivityCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ActivityHistoryItemOut(BaseModel):
    """One entry in the Activity modal's History tab. `kind` is "change" or
    "comment" for stored activity_events rows, and "version" for a difference
    derived from two consecutive schedule imports (see the route)."""

    kind: str
    created_at: datetime
    # The stored activity_events row, for comments — a mention links to it.
    event_id: uuid.UUID | None = None
    actor_name: str | None = None
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    body: str | None = None
    revision_label: str | None = None


class ScheduleImportUpdate(BaseModel):
    # The label and the data date are the editable metadata; activities and counts
    # come from the .xer itself and must keep matching it. At least one is required.
    revision_label: str | None = Field(default=None, min_length=1, max_length=30)
    data_date: date | None = None


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
    is_current: bool = False
    has_source_file: bool = False


class MentionableUserOut(BaseModel):
    """Someone who can be @-tagged on an activity — name and role, no email."""

    id: uuid.UUID
    full_name: str
    label: str
