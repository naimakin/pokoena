"""XER export support: wbs_nodes table + P6 identity fields (task_id/proj_id)

Revision ID: 0008_wbs_and_p6_identity
Revises: 0007_relationship_snapshots
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_wbs_and_p6_identity"
down_revision = "0007_relationship_snapshots"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["wbs_nodes"]


def upgrade() -> None:
    op.create_table(
        "wbs_nodes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("wbs_id", sa.String(50), nullable=False),
        sa.Column("parent_wbs_id", sa.String(50), nullable=True),
        sa.Column("wbs_short_name", sa.String(255), nullable=False),
        sa.Column("wbs_name", sa.String(255), nullable=False),
        sa.Column("seq_num", sa.Integer, nullable=True),
        sa.UniqueConstraint("project_id", "wbs_id", name="uq_wbs_nodes_project_wbs_id"),
    )
    op.create_index("ix_wbs_nodes_tenant_id", "wbs_nodes", ["tenant_id"])
    op.create_index("ix_wbs_nodes_project_id", "wbs_nodes", ["project_id"])

    op.add_column("activities", sa.Column("p6_task_id", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("p6_proj_id", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("p6_proj_short_name", sa.String(255), nullable=True))

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

    op.drop_column("projects", "p6_proj_short_name")
    op.drop_column("projects", "p6_proj_id")
    op.drop_column("activities", "p6_task_id")

    op.drop_table("wbs_nodes")
