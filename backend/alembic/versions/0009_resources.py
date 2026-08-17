"""EVM (quick engine) support: resources + resource_assignments

Revision ID: 0009_resources
Revises: 0008_wbs_and_p6_identity
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_resources"
down_revision = "0008_wbs_and_p6_identity"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["resources", "resource_assignments"]


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("rsrc_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(120), nullable=True),
        sa.Column("rsrc_type", sa.String(30), nullable=False, server_default="RT_Labor"),
        sa.Column("unit_id", sa.String(50), nullable=True),
        sa.Column("clndr_id", sa.String(50), nullable=True),
        sa.Column("curr_id", sa.String(50), nullable=True),
        sa.UniqueConstraint("project_id", "rsrc_id", name="uq_resources_project_rsrc_id"),
    )
    op.create_index("ix_resources_tenant_id", "resources", ["tenant_id"])
    op.create_index("ix_resources_project_id", "resources", ["project_id"])

    op.create_table(
        "resource_assignments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("remain_qty", sa.Float, nullable=False, server_default="0"),
        sa.Column("target_qty", sa.Float, nullable=False, server_default="0"),
        sa.Column("act_reg_qty", sa.Float, nullable=False, server_default="0"),
        sa.Column("target_cost", sa.Float, nullable=False, server_default="0"),
        sa.Column("act_reg_cost", sa.Float, nullable=False, server_default="0"),
        sa.Column("remain_cost", sa.Float, nullable=False, server_default="0"),
        sa.Column("unit_id", sa.String(50), nullable=True),
    )
    op.create_index("ix_resource_assignments_tenant_id", "resource_assignments", ["tenant_id"])
    op.create_index("ix_resource_assignments_project_id", "resource_assignments", ["project_id"])
    op.create_index("ix_resource_assignments_activity_id", "resource_assignments", ["activity_id"])

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
    for table_name in reversed(NEW_TENANT_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")

    op.drop_table("resource_assignments")
    op.drop_table("resources")
