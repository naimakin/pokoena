import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_projects_tenant_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # P6's own project identity, captured from the most recent .xer import
    # (services/xer_import.py) and written back verbatim on export
    # (engine/export/xer_writer.py) so a re-import into the SAME P6 project
    # is recognized as an update rather than a new project. None until a
    # schedule has been imported.
    p6_proj_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    p6_proj_short_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
