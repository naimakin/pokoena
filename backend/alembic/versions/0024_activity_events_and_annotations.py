"""Per-activity timeline (activity_events) + team annotations on activities.

Backs the Activity modal that replaced inline grid editing on Execution >
Progress: every field a user changes writes an `activity_events` row in the same
transaction, so the modal's History tab can show "who changed what" straight
after a save. Comments live in the same table (kind="comment") so the timeline
is one ordered list rather than two interleaved queries.

`is_important` / `tags` / `notes` are Poko's own annotations on a P6 activity —
deliberately outside the set of fields .xer import overwrites, so flagging an
activity survives every re-import of the programme.

Revision ID: 0024_activity_events
Revises: 0023_wbs_node_hidden
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_activity_events"
down_revision = "0023_wbs_node_hidden"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["activity_events"]

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("is_important", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "activities",
        sa.Column("tags", _JSON, nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("activities", sa.Column("notes", sa.Text, nullable=True))

    op.create_table(
        "activity_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "activity_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("field", sa.String(60), nullable=True),
        sa.Column("old_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_activity_events_tenant_id", "activity_events", ["tenant_id"])
    op.create_index("ix_activity_events_project_id", "activity_events", ["project_id"])
    op.create_index("ix_activity_events_actor_user_id", "activity_events", ["actor_user_id"])
    # The one query this table serves: one activity's timeline, newest first.
    op.create_index(
        "ix_activity_events_activity_created", "activity_events", ["activity_id", "created_at"]
    )

    if op.get_bind().dialect.name == "postgresql":
        for table_name in NEW_TENANT_SCOPED_TABLES:
            op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"""
                CREATE POLICY tenant_isolation ON {table_name}
                    FOR ALL
                    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
                    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
                """
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in reversed(NEW_TENANT_SCOPED_TABLES):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.drop_table("activity_events")
    op.drop_column("activities", "notes")
    op.drop_column("activities", "tags")
    op.drop_column("activities", "is_important")
