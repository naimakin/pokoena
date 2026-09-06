"""Configurable dashboard: per-user, per-project widget layout + colour theme

Revision ID: 0012_dashboard_layouts
Revises: 0011_activity_codes
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_dashboard_layouts"
down_revision = "0011_activity_codes"
branch_labels = None
depends_on = None

TABLE = "dashboard_layouts"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB if is_postgres else sa.JSON

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        # list of {key, order, enabled, options} — one entry per widget the
        # user has arranged; see api/routes/dashboard.py::DEFAULT_WIDGETS.
        sa.Column("widgets", json_type, nullable=False, server_default="[]"),
        sa.Column("theme_key", sa.String(30), nullable=False, server_default="calm"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "user_id", name="uq_dashboard_layouts_project_user"),
    )
    op.create_index("ix_dashboard_layouts_tenant_id", TABLE, ["tenant_id"])
    op.create_index("ix_dashboard_layouts_project_id", TABLE, ["project_id"])

    if is_postgres:
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {TABLE}
                FOR ALL
                USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
                WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {TABLE}")
    op.drop_index("ix_dashboard_layouts_project_id", table_name=TABLE)
    op.drop_index("ix_dashboard_layouts_tenant_id", table_name=TABLE)
    op.drop_table(TABLE)
