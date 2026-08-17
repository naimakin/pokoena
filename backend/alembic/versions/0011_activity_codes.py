"""Activity codes: activity_code_types, activity_code_values, task_activity_codes

Revision ID: 0011_activity_codes
Revises: 0010_evm_baseline
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_activity_codes"
down_revision = "0010_evm_baseline"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["activity_code_types", "activity_code_values", "task_activity_codes"]


def upgrade() -> None:
    op.create_table(
        "activity_code_types",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actv_code_type_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.UniqueConstraint("project_id", "actv_code_type_id", name="uq_activity_code_types_project_type_id"),
    )
    op.create_index("ix_activity_code_types_tenant_id", "activity_code_types", ["tenant_id"])
    op.create_index("ix_activity_code_types_project_id", "activity_code_types", ["project_id"])

    op.create_table(
        "activity_code_values",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("code_type_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activity_code_types.id"), nullable=False),
        sa.Column("actv_code_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(120), nullable=True),
        sa.Column("parent_actv_code_id", sa.String(50), nullable=True),
        sa.Column("seq_num", sa.Integer, nullable=True),
        sa.UniqueConstraint("project_id", "actv_code_id", name="uq_activity_code_values_project_code_id"),
    )
    op.create_index("ix_activity_code_values_tenant_id", "activity_code_values", ["tenant_id"])
    op.create_index("ix_activity_code_values_project_id", "activity_code_values", ["project_id"])
    op.create_index("ix_activity_code_values_code_type_id", "activity_code_values", ["code_type_id"])

    op.create_table(
        "task_activity_codes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("code_value_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activity_code_values.id"), nullable=False),
        sa.UniqueConstraint("activity_id", "code_value_id", name="uq_task_activity_codes_activity_code_value"),
    )
    op.create_index("ix_task_activity_codes_tenant_id", "task_activity_codes", ["tenant_id"])
    op.create_index("ix_task_activity_codes_project_id", "task_activity_codes", ["project_id"])
    op.create_index("ix_task_activity_codes_activity_id", "task_activity_codes", ["activity_id"])

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

    op.drop_table("task_activity_codes")
    op.drop_table("activity_code_values")
    op.drop_table("activity_code_types")
