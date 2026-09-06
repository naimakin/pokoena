"""Freeze P6 resources against a baseline: baseline_resources,
baseline_resource_assignments

Revision ID: 0013_baseline_resources
Revises: 0012_dashboard_layouts
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_baseline_resources"
down_revision = "0012_dashboard_layouts"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["baseline_resources", "baseline_resource_assignments"]


def upgrade() -> None:
    op.create_table(
        "baseline_resources",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("baseline_id", sa.Uuid(as_uuid=True), sa.ForeignKey("baselines.id"), nullable=False),
        sa.Column("rsrc_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(120), nullable=True),
        sa.Column("rsrc_type", sa.String(30), nullable=False, server_default="RT_Labor"),
        sa.Column("unit_id", sa.String(50), nullable=True),
        sa.UniqueConstraint("baseline_id", "rsrc_id", name="uq_baseline_resources_baseline_rsrc_id"),
    )
    op.create_index("ix_baseline_resources_tenant_id", "baseline_resources", ["tenant_id"])
    op.create_index("ix_baseline_resources_baseline_id", "baseline_resources", ["baseline_id"])

    op.create_table(
        "baseline_resource_assignments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("baseline_id", sa.Uuid(as_uuid=True), sa.ForeignKey("baselines.id"), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column(
            "baseline_resource_id", sa.Uuid(as_uuid=True), sa.ForeignKey("baseline_resources.id"), nullable=False
        ),
        sa.Column("target_qty", sa.Float, nullable=False, server_default="0"),
        sa.Column("target_cost", sa.Float, nullable=False, server_default="0"),
        sa.Column("unit_id", sa.String(50), nullable=True),
    )
    op.create_index("ix_baseline_resource_assignments_tenant_id", "baseline_resource_assignments", ["tenant_id"])
    op.create_index(
        "ix_baseline_resource_assignments_baseline_id", "baseline_resource_assignments", ["baseline_id"]
    )

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

    op.drop_table("baseline_resource_assignments")
    op.drop_table("baseline_resources")
