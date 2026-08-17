import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityCodeType(Base):
    """A P6 activity code type (ACTVTYPE) — e.g. "Phase", "Discipline",
    "Area". Imported from an .xer file's ACTVTYPE table."""

    __tablename__ = "activity_code_types"
    __table_args__ = (UniqueConstraint("project_id", "actv_code_type_id", name="uq_activity_code_types_project_type_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    actv_code_type_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ActivityCodeValue(Base):
    """One value within an activity code type (ACTVCODE) — e.g. "Phase 1"
    under the "Phase" type. `parent_actv_code_id` is a self-referential P6
    token (not a DB FK), same pattern as `WbsNode.parent_wbs_id`, forming an
    optional tree per code type."""

    __tablename__ = "activity_code_values"
    __table_args__ = (UniqueConstraint("project_id", "actv_code_id", name="uq_activity_code_values_project_code_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    code_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activity_code_types.id"), nullable=False, index=True)
    actv_code_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_actv_code_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    seq_num: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TaskActivityCode(Base):
    """Junction (TASKACTV): which ActivityCodeValue is assigned to which
    Activity. Replaced wholesale on every .xer import, same as
    ActivityRelationship/ResourceAssignment."""

    __tablename__ = "task_activity_codes"
    __table_args__ = (UniqueConstraint("activity_id", "code_value_id", name="uq_task_activity_codes_activity_code_value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), nullable=False, index=True)
    code_value_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activity_code_values.id"), nullable=False)
