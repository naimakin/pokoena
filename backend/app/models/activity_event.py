import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityEvent(Base):
    """Per-activity timeline: who changed which field, and who said what.

    Distinct from `audit_logs` on purpose. audit_logs is the security/compliance
    trail — logins, role changes, cross-tenant denials — written fire-and-forget
    through Celery, with no read path in the product. This is domain history that
    the Activity modal renders immediately after an edit, so it's written
    synchronously in the same transaction as the change it describes.

    One row per changed field (not per save), because that's the unit the
    timeline shows: "Start Date 02 Jul 2026 -> 08 Jul 2026". `kind="comment"`
    rows carry `body` instead and leave the field columns null.

    Schedule-import-driven changes are NOT stored here — they're derived on read
    by diffing consecutive `ScheduleImport.activities_snapshot` values (see
    api/routes/activities.py::activity_history), which keeps the import path
    untouched and makes the history work retroactively for programmes uploaded
    before this table existed.
    """

    __tablename__ = "activity_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null when the actor's user row is later deleted.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "change" | "comment"
    field: Mapped[str | None] = mapped_column(String(60), nullable=True)
    old_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
