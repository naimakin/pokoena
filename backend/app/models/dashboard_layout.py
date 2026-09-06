import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Generic JSON everywhere (needed for the SQLite test suite); real JSONB on Postgres.
_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class DashboardLayout(Base):
    """One row per (project, user): which Dashboard widgets that user has
    enabled, in what order, plus their chosen colour theme. No row means the
    user has never customised — the route serves a server-defined default
    (see api/routes/dashboard.py::DEFAULT_WIDGETS) rather than 404ing."""

    __tablename__ = "dashboard_layouts"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_dashboard_layouts_project_user"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # list[dict]: {"key": str, "order": int, "enabled": bool, "options": dict}
    widgets: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    theme_key: Mapped[str] = mapped_column(String(30), nullable=False, default="calm")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
