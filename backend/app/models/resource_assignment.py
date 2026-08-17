import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResourceAssignment(Base):
    """A P6 resource assignment imported from an .xer file's TASKRSRC table —
    one row per (activity, resource) pairing. `target_qty`/`act_reg_qty` (in
    hours, for RT_Labor) are the BAC/AC inputs to the quick EVM engine
    (engine/evm/evm_engine.py)."""

    __tablename__ = "resource_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id"), nullable=False)
    remain_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    act_reg_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    act_reg_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    remain_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
