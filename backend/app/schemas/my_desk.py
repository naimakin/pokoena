import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.activity import ActivityOut

InboxKind = Literal[
    "recovery_review",
    "recovery_revision",
    "flag_review",
    "mitigation_review",
    "mitigation_revision",
    "update_period",
]
InboxTone = Literal["crit", "warn", "info"]


class InboxItemOut(BaseModel):
    """One thing waiting on the caller, rolled up per project and kind — each
    links to the page where it's actually acted on."""

    kind: InboxKind
    project_id: uuid.UUID
    project_code: str
    project_name: str
    title: str
    detail: str | None = None
    count: int = 1
    due_at: datetime | None = None
    tone: InboxTone = "info"
    href: str


class PinOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_code: str
    project_name: str
    activity_external_id: str
    activity_name: str
    pinned_at: datetime
    pinned_finish: date | None
    pinned_total_float_hours: float | None
    pinned_hours_per_day: float | None
    pinned_revision_label: str | None
    # The live activity; None once the current programme no longer carries it.
    activity: ActivityOut | None = None
    # Shown finish today (actual once complete, else early) — and the deltas.
    finish: date | None = None
    drift_days: int | None = None  # finish − pinned_finish, calendar days
    # The same activity in the import before the current one ("since UPD-n").
    previous_revision_label: str | None = None
    previous_finish: date | None = None
    previous_total_float_hours: float | None = None
    note_count: int = 0


class SuggestionOut(BaseModel):
    activity: ActivityOut
    reason: str


class NoteContext(BaseModel):
    finish: date | None = None
    total_float_hours: float | None = None
    hours_per_day: float | None = None
    revision_label: str | None = None


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    project_id: uuid.UUID | None = None
    # When set, project_id is taken from the activity.
    activity_id: uuid.UUID | None = None
    remind_on: date | None = None

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("body cannot be blank")
        return v


class NoteUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    remind_on: date | None = None
    done: bool | None = None

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("body cannot be blank")
        return v


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    project_code: str | None = None
    activity_external_id: str | None
    activity_name: str | None
    body: str
    remind_on: date | None
    done_at: datetime | None
    context: NoteContext | None = None
    created_at: datetime
    updated_at: datetime


class ActivityDeskOut(BaseModel):
    """What the Activity modal needs from the caller's desk for one activity."""

    pinned: bool
    notes: list[NoteOut]
