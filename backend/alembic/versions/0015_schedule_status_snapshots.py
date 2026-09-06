"""Per-import project-status rollup (SPI / DCMA quality / recovery index /
verdicts) so Execution → Project Status can trend status across UPD-n.

Revision ID: 0015_schedule_status_snapshots
Revises: 0014_sync_revisions
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_schedule_status_snapshots"
down_revision = "0014_sync_revisions"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["schedule_status_snapshots"]


def upgrade() -> None:
    op.create_table(
        "schedule_status_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "schedule_import_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("schedule_imports.id"),
            nullable=False,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("data_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision_label", sa.String(30), nullable=True),
        sa.Column("spi", sa.Float, nullable=True),
        sa.Column("cpi", sa.Float, nullable=True),
        sa.Column("schedule_recovery_index", sa.Float, nullable=True),
        sa.Column("dcma_score", sa.Float, nullable=True),
        sa.Column("dcma_status", sa.String(10), nullable=True),
        sa.Column("activity_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("negative_float_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("overdue_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("percent_complete", sa.Float, nullable=False, server_default="0"),
        sa.Column("progress_verdict", sa.String(20), nullable=True),
        sa.Column("risk_verdict", sa.String(20), nullable=True),
        sa.Column("quality_verdict", sa.String(20), nullable=True),
        sa.UniqueConstraint("schedule_import_id", name="uq_schedule_status_snapshots_import"),
    )
    op.create_index(
        "ix_schedule_status_snapshots_tenant_id", "schedule_status_snapshots", ["tenant_id"]
    )
    op.create_index(
        "ix_schedule_status_snapshots_project_id", "schedule_status_snapshots", ["project_id"]
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

    # No backfill: computing DCMA/EVM inside a migration is fragile, and the
    # status route synthesises a live "current" point for the latest import
    # when it has no snapshot yet. The first persisted row lands on the next
    # .xer upload.


def downgrade() -> None:
    for table_name in reversed(NEW_TENANT_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.drop_table("schedule_status_snapshots")
