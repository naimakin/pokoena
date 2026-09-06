"""User-defined saved activity filters (Progress grid; view_key lets other
grids reuse the table later).

Revision ID: 0016_saved_activity_filters
Revises: 0015_schedule_status_snapshots
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_saved_activity_filters"
down_revision = "0015_schedule_status_snapshots"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["saved_activity_filters"]


def upgrade() -> None:
    op.create_table(
        "saved_activity_filters",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("view_key", sa.String(40), nullable=False, server_default="progress"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "criteria",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_shared", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("filter_version", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "project_id", "user_id", "view_key", "name",
            name="uq_saved_activity_filters_project_user_view_name",
        ),
    )
    op.create_index("ix_saved_activity_filters_tenant_id", "saved_activity_filters", ["tenant_id"])
    op.create_index("ix_saved_activity_filters_project_id", "saved_activity_filters", ["project_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
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
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table_name in reversed(NEW_TENANT_SCOPED_TABLES):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.drop_table("saved_activity_filters")
