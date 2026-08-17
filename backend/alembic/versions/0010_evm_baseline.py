"""EVM baseline-lock + S-curve time series: baselines, baseline_activities,
baseline_pv_curve, progress_entries, evm_snapshots

Revision ID: 0010_evm_baseline
Revises: 0009_resources
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_evm_baseline"
down_revision = "0009_resources"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["baselines", "baseline_activities", "baseline_pv_curve", "progress_entries", "evm_snapshots"]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    baseline_status = postgresql.ENUM("draft", "active", "superseded", name="baseline_status")
    progress_entry_type = postgresql.ENUM("actual", "correction", "forecast", name="progress_entry_type")
    if is_postgres:
        baseline_status.create(bind, checkfirst=True)
        progress_entry_type.create(bind, checkfirst=True)

    def no_create(enum_type):
        return postgresql.ENUM(*enum_type.enums, name=enum_type.name, create_type=False)

    op.create_table(
        "baselines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("schedule_import_id", sa.Uuid(as_uuid=True), sa.ForeignKey("schedule_imports.id"), nullable=False),
        sa.Column("version_label", sa.String(120), nullable=False, server_default="Target-1"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("total_budget_manhours", sa.Float, nullable=False),
        sa.Column("target_start_date", sa.Date, nullable=False),
        sa.Column("target_end_date", sa.Date, nullable=False),
        sa.Column("distribution_method", sa.String(30), nullable=False, server_default="linear"),
        sa.Column("status", no_create(baseline_status), nullable=False, server_default="draft"),
        sa.Column("activity_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "version_label", name="uq_baselines_project_version_label"),
    )
    op.create_index("ix_baselines_tenant_id", "baselines", ["tenant_id"])
    op.create_index("ix_baselines_project_id", "baselines", ["project_id"])

    op.create_table(
        "baseline_activities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("baseline_id", sa.Uuid(as_uuid=True), sa.ForeignKey("baselines.id"), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("planned_manhours", sa.Float, nullable=False, server_default="0"),
        sa.Column("baseline_start", sa.Date, nullable=True),
        sa.Column("baseline_end", sa.Date, nullable=True),
        sa.Column("wbs_code", sa.String(50), nullable=True),
        sa.UniqueConstraint("baseline_id", "activity_id", name="uq_baseline_activities_baseline_activity"),
    )
    op.create_index("ix_baseline_activities_tenant_id", "baseline_activities", ["tenant_id"])
    op.create_index("ix_baseline_activities_baseline_id", "baseline_activities", ["baseline_id"])

    op.create_table(
        "baseline_pv_curve",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("baseline_id", sa.Uuid(as_uuid=True), sa.ForeignKey("baselines.id"), nullable=False),
        sa.Column("curve_date", sa.Date, nullable=False),
        sa.Column("pv_daily", sa.Float, nullable=False, server_default="0"),
        sa.Column("pv_cumulative", sa.Float, nullable=False, server_default="0"),
        sa.UniqueConstraint("baseline_id", "curve_date", name="uq_baseline_pv_curve_baseline_date"),
    )
    op.create_index("ix_baseline_pv_curve_tenant_id", "baseline_pv_curve", ["tenant_id"])
    op.create_index("ix_baseline_pv_curve_baseline_id", "baseline_pv_curve", ["baseline_id"])

    op.create_table(
        "progress_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("burned_manhours_daily", sa.Float, nullable=False),
        sa.Column("physical_pct_snapshot", sa.Float, nullable=True),
        sa.Column("entry_type", no_create(progress_entry_type), nullable=False, server_default="actual"),
        sa.Column("crew_size", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("is_out_of_sequence", sa.Boolean, nullable=False, server_default="false"),
        sa.UniqueConstraint("project_id", "activity_id", "entry_date", name="uq_progress_entries_project_activity_date"),
    )
    op.create_index("ix_progress_entries_tenant_id", "progress_entries", ["tenant_id"])
    op.create_index("ix_progress_entries_project_id", "progress_entries", ["project_id"])
    op.create_index("ix_progress_entries_activity_id", "progress_entries", ["activity_id"])

    op.create_table(
        "evm_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("baseline_id", sa.Uuid(as_uuid=True), sa.ForeignKey("baselines.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("pv_cumulative", sa.Float, nullable=True),
        sa.Column("ev_cumulative", sa.Float, nullable=True),
        sa.Column("ac_cumulative", sa.Float, nullable=True),
        sa.Column("spi", sa.Float, nullable=True),
        sa.Column("cpi", sa.Float, nullable=True),
        sa.Column("sv", sa.Float, nullable=True),
        sa.Column("cv", sa.Float, nullable=True),
        sa.Column("bac", sa.Float, nullable=True),
        sa.Column("eac", sa.Float, nullable=True),
        sa.Column("etc", sa.Float, nullable=True),
        sa.Column("tcpi", sa.Float, nullable=True),
        sa.Column("percent_complete_planned", sa.Float, nullable=True),
        sa.Column("percent_complete_earned", sa.Float, nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "baseline_id", "snapshot_date", name="uq_evm_snapshots_project_baseline_date"),
    )
    op.create_index("ix_evm_snapshots_tenant_id", "evm_snapshots", ["tenant_id"])
    op.create_index("ix_evm_snapshots_project_id", "evm_snapshots", ["project_id"])

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

    op.drop_table("evm_snapshots")
    op.drop_table("progress_entries")
    op.drop_table("baseline_pv_curve")
    op.drop_table("baseline_activities")
    op.drop_table("baselines")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="progress_entry_type").drop(bind, checkfirst=True)
        sa.Enum(name="baseline_status").drop(bind, checkfirst=True)
