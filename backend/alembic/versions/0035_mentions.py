"""@mentions in activity comments.

mentions — one row per person tagged in a comment (activity_events kind
"comment"); their My Desk lists the unread ones. Tenant-isolated by RLS like
every tenant table; privacy between users is the application's
mentioned_user_id filter (as personal_notes).

Revision ID: 0035_mentions
Revises: 0034_menu_roles
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0035_mentions"
down_revision = "0034_menu_roles"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["mentions"]


def upgrade() -> None:
    op.create_table(
        "mentions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "activity_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("activity_external_id", sa.String(50), nullable=False),
        sa.Column(
            "activity_event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("activity_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mentioned_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "author_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("activity_event_id", "mentioned_user_id", name="uq_mentions_event_user"),
    )
    op.create_index("ix_mentions_tenant_id", "mentions", ["tenant_id"])
    op.create_index("ix_mentions_project_id", "mentions", ["project_id"])
    op.create_index("ix_mentions_activity_id", "mentions", ["activity_id"])
    op.create_index("ix_mentions_activity_event_id", "mentions", ["activity_event_id"])
    op.create_index("ix_mentions_mentioned_user_id", "mentions", ["mentioned_user_id"])

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
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON mentions")
    op.drop_table("mentions")
