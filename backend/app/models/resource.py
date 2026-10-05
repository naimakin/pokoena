import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# P6 RSRC.rsrc_type values, exactly as P6 writes them (checked against P6
# Professional's own database and real exports). Labor units roll up into
# TASK.*_work_qty and drive the units %; nonlabor into TASK.*_equip_qty;
# material has no activity-level total.
LABOR = "RT_Labor"
NONLABOR = "RT_Equip"
MATERIAL = "RT_Mat"


class Resource(Base):
    """A P6 resource (labor/material/equipment) imported from an .xer file's
    RSRC table. Feeds the quick EVM engine (engine/evm/evm_engine.py) and
    DCMA check #10 (resource-assignment coverage)."""

    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("project_id", "rsrc_id", name="uq_resources_project_rsrc_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    rsrc_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rsrc_type: Mapped[str] = mapped_column(String(30), nullable=False, default="RT_Labor")
    unit_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    clndr_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    curr_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
