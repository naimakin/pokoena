"""Schedule Simulation: saved what-if scenarios.

schedule_simulations keeps a scenario's inputs only — a simulation data date
and the hypothetical changes, keyed by activity ID — plus the last run's
project-finish delta for the list. Results are recomputed on every run
(services/schedule_simulation.py), since the live programme changes with every
update.

Revision ID: 0029_schedule_simulations
Revises: 0028_progress_pct_and_site_risk
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_schedule_simulations"
down_revision = "0028_progress_pct_and_site_risk"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["schedule_simulations"]

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "schedule_simulations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("simulation_data_date", sa.Date, nullable=True),
        sa.Column("edits", _JSON, nullable=False, server_default=sa.text("'[]'")),
        # Not a FK: the import the scenario last ran on (see risk_simulation_runs).
        sa.Column("schedule_import_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("revision_label", sa.String(30), nullable=True),
        sa.Column("last_finish_delta_days", sa.Float, nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_schedule_simulations_tenant_id", "schedule_simulations", ["tenant_id"])
    op.create_index("ix_schedule_simulations_project_id", "schedule_simulations", ["project_id"])

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
    op.drop_table("schedule_simulations")
