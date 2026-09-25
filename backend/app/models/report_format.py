import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Generic JSON everywhere (needed for the SQLite test suite); real JSONB on Postgres.
_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class ReportFormat(Base):
    """A named, saved selection of report blocks — "Monthly Progress Report",
    "Executive Summary", whatever the team calls theirs. Rendering one produces
    the printable report at /reporting/report/{id}.

    Shaped deliberately like `dashboard_layout.py`: the same
    `[{key, order, enabled, options}]` block list against a server-side
    catalogue (`api/routes/reports.py::REPORT_BLOCK_KEYS`), so the two
    configure UIs stay recognisably the same thing. The differences are that a
    format belongs to the project rather than to one user — reports are handed
    between planners, and the format is part of what gets agreed with the
    client — and that it carries page setup, because this one goes on paper.
    """

    __tablename__ = "report_formats"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_report_formats_project_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # list[dict]: {"key": str, "order": int, "enabled": bool, "options": dict}
    blocks: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    # {"orientation": "portrait"|"landscape", "paper": "A4"|"Letter"}
    page_setup: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)

    # Seeded presets are created on first use rather than by migration, so a
    # project that already existed gets them too. The flag is what lets the UI
    # say "this is one of the standard formats" and lets a reseed skip them.
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # The editable narrative that goes in the Executive summary block. A report
    # with no words in it is not a report — every other block is generated.
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
