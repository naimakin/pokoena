import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReportBlockConfig(BaseModel):
    key: str
    order: int
    enabled: bool = True
    options: dict = Field(default_factory=dict)


class ReportBlockCatalogueOut(BaseModel):
    """One entry of the server-side block catalogue. The frontend registry
    (components/reporting/ReportBlocks.tsx) maps `key` to a component; this
    supplies the label, the blurb the builder shows next to the checkbox, and
    what the block needs before it can render anything."""

    key: str
    title: str
    description: str
    # "baseline" | "two_imports" | "resources" | None — what the block needs
    # before it has anything to show, so the builder can warn up front rather
    # than the report coming out with an empty panel in it.
    requires: str | None = None
    default_options: dict = Field(default_factory=dict)


class ReportFormatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    blocks: list[ReportBlockConfig]
    page_setup: dict
    is_preset: bool
    narrative: str | None
    created_at: datetime
    updated_at: datetime


class ReportFormatCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    blocks: list[ReportBlockConfig] = Field(default_factory=list)
    page_setup: dict = Field(default_factory=dict)
    narrative: str | None = None


class ReportFormatUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    blocks: list[ReportBlockConfig] | None = None
    page_setup: dict | None = None
    narrative: str | None = None


class ReportHeaderOut(BaseModel):
    """What goes on every page of every report, whatever blocks it contains.
    Owners reject reports over exactly these fields — see the page footer."""

    project_id: uuid.UUID
    project_name: str
    project_code: str | None
    data_date: datetime | None
    schedule_revision: str | None
    schedule_filename: str | None
    imported_at: datetime | None
    baseline_label: str | None
    baseline_changed_since: bool
    # How percent complete is arrived at. Stated on the report because an
    # unstated basis is how a contractor claims 60% and an owner measures 35%.
    progress_basis: str
    generated_at: datetime
    generated_by: str | None
