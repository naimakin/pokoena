"""Reporting: report_formats — a named, saved selection of report blocks that
renders to a printable report.

Revision ID: 0025_report_formats
Revises: 0024_activity_events
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_report_formats"
down_revision = "0024_activity_events"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["report_formats"]

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "report_formats",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("blocks", _JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("page_setup", _JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_preset", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("narrative", sa.Text, nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "name", name="uq_report_formats_project_name"),
    )
    op.create_index("ix_report_formats_tenant_id", "report_formats", ["tenant_id"])
    op.create_index("ix_report_formats_project_id", "report_formats", ["project_id"])

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
    op.drop_table("report_formats")
