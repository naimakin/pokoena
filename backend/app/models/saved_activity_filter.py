import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Generic JSON everywhere (needed for the SQLite test suite); real JSONB on Postgres.
_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class SavedActivityFilter(Base):
    """One named, reusable activity filter a user built on a grid page
    (Progress today; `view_key` lets Schedule/Gantt reuse the table later).
    `criteria` is an opaque client-owned blob — the backend never parses it
    beyond a size check; the frontend evaluates it against the loaded activity
    list. `filter_version` lets the client migrate an old blob shape on read.
    Modelled on `dashboard_layouts` (per-project-per-user JSON config)."""

    __tablename__ = "saved_activity_filters"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", "view_key", "name",
            name="uq_saved_activity_filters_project_user_view_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)  # owner
    view_key: Mapped[str] = mapped_column(String(40), nullable=False, default="progress")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    criteria: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filter_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
