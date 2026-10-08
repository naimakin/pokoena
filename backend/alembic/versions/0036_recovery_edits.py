"""Recovery plans stay editable; @mentions and owners in recovery plans.

- recovery_plans.edited_at / edited_by_user_id — the last change to what the
  author wrote (root cause, action items). Editing no longer depends on the
  plan's status, and doesn't change it; the page flags an edit made after
  submission or acknowledgement from these two columns.
- recovery_plan_items.owner_user_id — an action's owner picked from the people
  who can see the activity (owner_name stays for free text and display).
- mentions: a mention can now come from a recovery plan as well as an activity
  comment. activity_event_id becomes nullable; kind says which source, and
  recovery_plan_id / recovery_item_id point at it. Existing rows are comments.
  The table is already tenant-isolated by RLS (0035); no policy change.

Revision ID: 0036_recovery_edits
Revises: 0035_mentions
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_recovery_edits"
down_revision = "0035_mentions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recovery_plans", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "recovery_plans",
        sa.Column(
            "edited_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.add_column(
        "recovery_plan_items",
        sa.Column(
            "owner_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_recovery_plan_items_owner_user_id", "recovery_plan_items", ["owner_user_id"])

    op.alter_column("mentions", "activity_event_id", existing_type=sa.Uuid(as_uuid=True), nullable=True)
    op.add_column(
        "mentions",
        sa.Column("kind", sa.String(30), nullable=False, server_default="comment"),
    )
    op.add_column(
        "mentions",
        sa.Column(
            "recovery_plan_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("recovery_plans.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "mentions",
        sa.Column(
            "recovery_item_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("recovery_plan_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_mentions_recovery_plan_id", "mentions", ["recovery_plan_id"])
    op.create_index("ix_mentions_recovery_item_id", "mentions", ["recovery_item_id"])


def downgrade() -> None:
    op.drop_index("ix_mentions_recovery_item_id", table_name="mentions")
    op.drop_index("ix_mentions_recovery_plan_id", table_name="mentions")
    op.execute("DELETE FROM mentions WHERE activity_event_id IS NULL")
    op.drop_column("mentions", "recovery_item_id")
    op.drop_column("mentions", "recovery_plan_id")
    op.drop_column("mentions", "kind")
    op.alter_column("mentions", "activity_event_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    op.drop_index("ix_recovery_plan_items_owner_user_id", table_name="recovery_plan_items")
    op.drop_column("recovery_plan_items", "owner_user_id")
    op.drop_column("recovery_plans", "edited_by_user_id")
    op.drop_column("recovery_plans", "edited_at")
