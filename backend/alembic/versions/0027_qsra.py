"""Risk: quantitative schedule risk analysis (QSRA).

- risk_items gains what a risk needs to enter the Monte Carlo: probability as a
  %, a 3-point impact (as a % stretch of the linked activities' durations, or
  as working days of delay), its distribution, threat vs opportunity, the
  post-mitigation values, and whether the impact is already in the P6 schedule
  (so it isn't counted twice). Plain strings rather than Postgres enums for the
  new categorical fields — they're validated at the API, and adding a value
  later shouldn't need a type migration.
- risk_analysis_settings: one row per project (confidence level, iterations,
  seed, target date, finish milestone, near-critical threshold).
- risk_simulation_runs: every run, persisted with a frozen copy of its inputs,
  so results are reproducible and P-dates can be trended across updates.
- schedule_imports.assignments_snapshot: per-import copy of the resource
  assignments. resource_assignments is replaced wholesale on every import, so
  without this there is no productivity history — and history not captured now
  is lost for good.

Revision ID: 0027_qsra
Revises: 0026_export_source_import
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_qsra"
down_revision = "0026_export_source_import"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["risk_analysis_settings", "risk_simulation_runs"]

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    add = lambda col: op.add_column("risk_items", col)  # noqa: E731
    add(sa.Column("qsra_enabled", sa.Boolean, nullable=False, server_default=sa.false()))
    add(sa.Column("risk_kind", sa.String(20), nullable=False, server_default="threat"))
    add(sa.Column("probability_pct", sa.Float, nullable=True))
    add(sa.Column("impact_mode", sa.String(20), nullable=False, server_default="duration_pct"))
    add(sa.Column("impact_min", sa.Float, nullable=True))
    add(sa.Column("impact_ml", sa.Float, nullable=True))
    add(sa.Column("impact_max", sa.Float, nullable=True))
    add(sa.Column("impact_distribution", sa.String(20), nullable=False, server_default="triangular"))
    add(sa.Column("post_probability_pct", sa.Float, nullable=True))
    add(sa.Column("post_impact_min", sa.Float, nullable=True))
    add(sa.Column("post_impact_ml", sa.Float, nullable=True))
    add(sa.Column("post_impact_max", sa.Float, nullable=True))
    add(sa.Column("impact_in_schedule", sa.Boolean, nullable=False, server_default=sa.false()))
    add(sa.Column("apply_to_wbs", sa.Boolean, nullable=False, server_default=sa.false()))

    op.add_column(
        "schedule_imports",
        sa.Column("assignments_snapshot", _JSON, nullable=False, server_default=sa.text("'[]'")),
    )

    op.create_table(
        "risk_analysis_settings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("iterations", sa.Integer, nullable=False, server_default="1000"),
        sa.Column("seed", sa.Integer, nullable=False, server_default="20260929"),
        sa.Column("target_date", sa.Date, nullable=True),
        sa.Column("finish_activity_external_id", sa.String(50), nullable=True),
        sa.Column("near_critical_days", sa.Float, nullable=False, server_default="10"),
        sa.Column("correlate_by_wbs", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", name="uq_risk_analysis_settings_project"),
    )
    op.create_index("ix_risk_analysis_settings_tenant_id", "risk_analysis_settings", ["tenant_id"])

    op.create_table(
        "risk_simulation_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        # Not a FK: a run outlives the import it was made on (deleting an old
        # update mustn't erase the confidence trend), and it keeps its own copy
        # of the data date and label below.
        sa.Column("schedule_import_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("revision_label", sa.String(30), nullable=True),
        sa.Column("data_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("iterations", sa.Integer, nullable=False),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("settings", _JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("inputs", _JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("results", _JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("ranking", _JSON, nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_risk_simulation_runs_tenant_id", "risk_simulation_runs", ["tenant_id"])
    op.create_index("ix_risk_simulation_runs_project_id", "risk_simulation_runs", ["project_id"])

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
    op.drop_table("risk_simulation_runs")
    op.drop_table("risk_analysis_settings")
    op.drop_column("schedule_imports", "assignments_snapshot")
    for col in (
        "apply_to_wbs", "impact_in_schedule", "post_impact_max", "post_impact_ml", "post_impact_min",
        "post_probability_pct", "impact_distribution", "impact_max", "impact_ml", "impact_min", "impact_mode",
        "probability_pct", "risk_kind", "qsra_enabled",
    ):
        op.drop_column("risk_items", col)
