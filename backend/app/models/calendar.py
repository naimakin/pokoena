import uuid

import sqlalchemy as sa
from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Generic JSON everywhere (needed for the SQLite test suite); real JSONB on Postgres.
_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class Calendar(Base):
    """A P6 calendar imported from an .xer file. `work_week`/`exceptions` store
    the same shift-list shape the CPM engine's CalendarEngine expects, serialized
    as JSON (see app.parser.xer_models.Calendar) rather than normalized — keeps
    the parser/scheduler port working against a stable shape."""

    __tablename__ = "calendars"
    __table_args__ = (UniqueConstraint("project_id", "clndr_id", name="uq_calendars_project_clndr_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    clndr_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hours_per_day: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    work_week: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    exceptions: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
