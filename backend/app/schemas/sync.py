import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ScheduleExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    revision_no: int
    revision_label: str
    source_filename: str
    data_date: datetime | None
    activity_count: int
    exported_by_user_id: uuid.UUID
    exported_at: datetime


class SyncLogEntry(BaseModel):
    """One row of the combined Export / Sync to P6 timeline — an export or an
    import, newest first."""

    kind: Literal["export", "import"]
    id: uuid.UUID
    label: str
    at: datetime
    user_id: uuid.UUID
    user_name: str | None = None
    activity_count: int
    data_date: datetime | None
    filename: str
    # Only set on an import the user linked back to a Poko export.
    linked_export_label: str | None = None
