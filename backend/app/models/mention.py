import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Mention(Base):
    """Someone @-tagged in an activity comment (services/mentions.py). It is
    that person's notification: My Desk lists their unread ones. Keyed on the
    P6 activity ID as well as the row, so it follows a renamed activity
    through a re-import like pins and recovery plans do."""

    __tablename__ = "mentions"
    __table_args__ = (UniqueConstraint("activity_event_id", "mentioned_user_id", name="uq_mentions_event_user"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activity_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mentioned_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
