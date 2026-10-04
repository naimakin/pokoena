import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class ActivityPin(Base):
    """An activity one user pinned to their own My Desk (Execution → My Desk).
    Private to that user: RLS isolates the tenant, and every query also
    filters on `user_id` (same split as saved_activity_filters).

    Keyed on `activity_external_id` (the P6 task_code), not the activity UUID,
    for the same reason as RecoveryPlan: it survives a re-import, and
    `xer_import.py` re-links it when P6 renames the activity. The pinned_*
    columns freeze the activity at the moment of pinning so the desk can show
    "drift since pinned"."""

    __tablename__ = "activity_pins"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "activity_external_id", name="uq_activity_pins_user_project_activity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    activity_external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    pinned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    pinned_total_float_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    pinned_hours_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    pinned_revision_label: Mapped[str | None] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PersonalNote(Base):
    """A private note on My Desk — free-standing, on a project, or on one
    activity — optionally with a reminder date. Only its author ever reads it;
    there is no admin read path.

    `context` freezes the activity's finish / total float / revision when the
    note was written ("written at UPD-7: finish 12-Jun, TF 4d") so the note can
    be read against today's values."""

    __tablename__ = "personal_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # Null = a general note, shown whichever project is selected.
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    activity_external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    activity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    remind_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict | None] = mapped_column(_JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
