import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class AuditLog(Base):
    """Every login, cross-tenant/cross-scope access attempt, role/permission
    change, and platform support-access query. `tenant_id` is null only for
    pure platform-level events (e.g. a platform admin's own login)."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    # Named event_metadata, not metadata: `metadata` is reserved on Declarative models.
    event_metadata: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
