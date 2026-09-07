import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.logic_diff import LogicDiffChangeOut, LogicDiffSummaryOut


class ChangeImportRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    revision_label: str | None
    data_date: datetime | None
    imported_at: datetime


class FieldChangeOut(BaseModel):
    field: str
    label: str
    old: str | int | float | None
    new: str | int | float | None
    delta_days: int | float | None = None
    delta_hours: float | None = None


class ActivityChangeOut(BaseModel):
    external_id: str
    name: str | None
    wbs_path: str | None
    is_critical: bool
    fields: list[FieldChangeOut]


class AddedActivityOut(BaseModel):
    external_id: str
    name: str | None
    wbs_path: str | None
    planned_finish: str | None
    is_critical: bool


class RemovedActivityOut(BaseModel):
    external_id: str
    name: str | None
    was_critical: bool


class RenamedActivityOut(BaseModel):
    old_external_id: str
    new_external_id: str
    name: str | None


class ChangeSummaryOut(BaseModel):
    activities_added: int
    activities_removed: int
    activities_renamed: int
    activities_modified: int
    date_changes: int
    criticality_changes: int
    relationships_added: int
    relationships_removed: int
    relationships_modified: int


class ChangeActivitiesOut(BaseModel):
    added: list[AddedActivityOut]
    removed: list[RemovedActivityOut]
    renamed: list[RenamedActivityOut]
    modified: list[ActivityChangeOut]


class ChangeRelationshipsOut(BaseModel):
    summary: LogicDiffSummaryOut
    changes: list[LogicDiffChangeOut]


class ScheduleChangeReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    comparison_basis: Literal["previous_upd", "baseline_programme", "baseline_frozen", "none"]
    from_import: ChangeImportRefOut | None
    to_import: ChangeImportRefOut | None
    coverage: dict
    thresholds: dict
    summary: ChangeSummaryOut
    activities: ChangeActivitiesOut
    relationships: ChangeRelationshipsOut
