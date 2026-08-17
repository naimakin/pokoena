import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum as SAEnum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    complete = "complete"


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    project_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_scopes.id"), nullable=True, index=True
    )
    external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    discipline: Mapped[str] = mapped_column(String(120), nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    percent_complete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[ActivityStatus] = mapped_column(
        SAEnum(ActivityStatus, name="activity_status"),
        nullable=False,
        default=ActivityStatus.not_started,
    )

    # --- P6/CPM fields, populated by .xer import (backend/app/services/xer_import.py). ---
    # `remaining_duration_days` above stays the field the subcontractor scope page
    # reads/writes; these are read-only, CPM-derived, and overwritten wholesale on
    # every re-import (see xer_import.py for the exact create-vs-update field policy).
    clndr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calendars.id"), nullable=True, index=True)
    wbs_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    remaining_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    early_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    early_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    late_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    late_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_float_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_float_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    constraint_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    constraint_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_imports.id"), nullable=True, index=True
    )
