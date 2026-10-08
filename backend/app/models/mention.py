import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MentionKind:
    """What a mention points at. A plain string column (not a DB enum) so a new
    source doesn't need an ALTER TYPE."""

    comment = "comment"  # an activity comment (activity_event_id)
    recovery_root_cause = "recovery_root_cause"  # a recovery plan's root cause (recovery_plan_id)
    recovery_action = "recovery_action"  # a recovery action's text (recovery_item_id)
    recovery_owner = "recovery_owner"  # made the owner of a recovery action (recovery_item_id)

    RECOVERY = ("recovery_root_cause", "recovery_action", "recovery_owner")


class Mention(Base):
    """Someone @-tagged in an activity comment or a recovery plan, or made the
    owner of a recovery action (services/mentions.py). It is that person's
    notification: My Desk lists their unread ones. Keyed on the P6 activity ID
    as well as the row, so it follows a renamed activity through a re-import
    like pins and recovery plans do.

    Exactly one source is set: `activity_event_id` for a comment,
    `recovery_plan_id` (+ `recovery_item_id` for an action) for a recovery plan."""

    __tablename__ = "mentions"
    __table_args__ = (UniqueConstraint("activity_event_id", "mentioned_user_id", name="uq_mentions_event_user"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activity_events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default=MentionKind.comment, server_default="comment")
    recovery_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recovery_plans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    recovery_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recovery_plan_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    mentioned_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
