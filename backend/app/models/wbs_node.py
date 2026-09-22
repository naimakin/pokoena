import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WbsNode(Base):
    """A WBS (work breakdown structure) node imported from an .xer file's
    PROJWBS table. Persisted only so XER export (engine/export/xer_writer.py)
    can round-trip a project's WBS tree — nothing in CPM scheduling, DCMA, or
    the other engines reads this table."""

    __tablename__ = "wbs_nodes"
    __table_args__ = (UniqueConstraint("project_id", "wbs_id", name="uq_wbs_nodes_project_wbs_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    wbs_id: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_wbs_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wbs_short_name: Mapped[str] = mapped_column(String(255), nullable=False)
    wbs_name: Mapped[str] = mapped_column(String(255), nullable=False)
    seq_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Only ever set on a ROOT node (no parent). Hides that whole subtree from
    # Planning > WBS without deleting anything — the escape hatch for a project
    # that already had two unrelated programs' WBS trees accumulate live before
    # the per-import wholesale-replace existed (see services/xer_import.py):
    # re-importing the CURRENT program alone doesn't retroactively know which
    # already-live root was the stale one, so the human picks. Survives being
    # upserted again by a later import of the same wbs_id (never reset there).
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
