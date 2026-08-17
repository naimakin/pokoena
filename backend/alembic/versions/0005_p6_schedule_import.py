"""P6 schedule import: calendars, schedule_imports, CPM fields on activities

Revision ID: 0005_p6_schedule_import
Revises: 0004_multi_project_roles
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_p6_schedule_import"
down_revision = "0004_multi_project_roles"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["calendars", "schedule_imports"]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB if is_postgres else sa.JSON

    op.create_table(
        "calendars",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("clndr_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hours_per_day", sa.Float, nullable=False, server_default="8"),
        sa.Column("work_week", json_type, nullable=False, server_default="[]"),
        sa.Column("exceptions", json_type, nullable=False, server_default="[]"),
        sa.UniqueConstraint("project_id", "clndr_id", name="uq_calendars_project_clndr_id"),
    )
    op.create_index("ix_calendars_tenant_id", "calendars", ["tenant_id"])
    op.create_index("ix_calendars_project_id", "calendars", ["project_id"])

    op.create_table(
        "schedule_imports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("data_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("activity_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("warnings", json_type, nullable=False, server_default="[]"),
    )
    op.create_index("ix_schedule_imports_tenant_id", "schedule_imports", ["tenant_id"])
    op.create_index("ix_schedule_imports_project_id", "schedule_imports", ["project_id"])

    op.add_column("activities", sa.Column("clndr_id", sa.Uuid(as_uuid=True), sa.ForeignKey("calendars.id"), nullable=True))
    op.add_column("activities", sa.Column("wbs_path", sa.String(500), nullable=True))
    op.add_column("activities", sa.Column("task_type", sa.String(30), nullable=True))
    op.add_column("activities", sa.Column("status_code", sa.String(30), nullable=True))
    op.add_column("activities", sa.Column("target_duration_hours", sa.Float, nullable=True))
    op.add_column("activities", sa.Column("remaining_duration_hours", sa.Float, nullable=True))
    op.add_column("activities", sa.Column("early_start", sa.Date, nullable=True))
    op.add_column("activities", sa.Column("early_finish", sa.Date, nullable=True))
    op.add_column("activities", sa.Column("late_start", sa.Date, nullable=True))
    op.add_column("activities", sa.Column("late_finish", sa.Date, nullable=True))
    op.add_column("activities", sa.Column("total_float_hours", sa.Float, nullable=True))
    op.add_column("activities", sa.Column("free_float_hours", sa.Float, nullable=True))
    op.add_column("activities", sa.Column("is_critical", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("activities", sa.Column("constraint_type", sa.String(30), nullable=True))
    op.add_column("activities", sa.Column("constraint_date", sa.Date, nullable=True))
    op.add_column(
        "activities",
        sa.Column("last_import_id", sa.Uuid(as_uuid=True), sa.ForeignKey("schedule_imports.id"), nullable=True),
    )
    op.create_index("ix_activities_clndr_id", "activities", ["clndr_id"])
    op.create_index("ix_activities_last_import_id", "activities", ["last_import_id"])

    op.add_column("activity_relationships", sa.Column("lag_hours", sa.Integer, nullable=True))

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

    op.drop_column("activity_relationships", "lag_hours")

    op.drop_index("ix_activities_last_import_id", table_name="activities")
    op.drop_index("ix_activities_clndr_id", table_name="activities")
    op.drop_column("activities", "last_import_id")
    op.drop_column("activities", "constraint_date")
    op.drop_column("activities", "constraint_type")
    op.drop_column("activities", "is_critical")
    op.drop_column("activities", "free_float_hours")
    op.drop_column("activities", "total_float_hours")
    op.drop_column("activities", "late_finish")
    op.drop_column("activities", "late_start")
    op.drop_column("activities", "early_finish")
    op.drop_column("activities", "early_start")
    op.drop_column("activities", "remaining_duration_hours")
    op.drop_column("activities", "target_duration_hours")
    op.drop_column("activities", "status_code")
    op.drop_column("activities", "task_type")
    op.drop_column("activities", "wbs_path")
    op.drop_column("activities", "clndr_id")

    op.drop_table("schedule_imports")
    op.drop_table("calendars")
