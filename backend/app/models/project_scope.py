import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectScope(Base):
    """A subset of a project's schedule activities (typically one discipline,
    e.g. 'MEP - Level 2'). This is the unit subcontractors get assigned to via
    SubcontractorScopeAssignment; Activity.project_scope_id points here.

    `subcontractor_org_id` records which firm a scope belongs to (for
    dashboard/reporting grouping) — it's a labeling convenience, not an access
    control mechanism: access is still granted per-user via
    SubcontractorScopeAssignment regardless of which org a scope is tagged with.
    """

    __tablename__ = "project_scopes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    subcontractor_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcontractor_organizations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    discipline: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
