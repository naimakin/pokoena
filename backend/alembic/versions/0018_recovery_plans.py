"""Recovery plans + itemised action items (Execution → Recovery Plan).

Revision ID: 0018_recovery_plans
Revises: 0017_activities_snapshot
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_recovery_plans"
down_revision = "0017_activities_snapshot"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["recovery_plans", "recovery_plan_items"]

_PLAN_STATUS = sa.Enum("draft", "submitted", "accepted", "needs_revision", name="recovery_plan_status")
_ITEM_STATUS = sa.Enum("open", "in_progress", "done", "dropped", name="recovery_item_status")


def upgrade() -> None:
    op.create_table(
        "recovery_plans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("activity_external_id", sa.String(50), nullable=False),
        sa.Column("p6_task_id", sa.String(50), nullable=True),
        sa.Column(
            "activity_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("activity_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("wbs_path", sa.String(500), nullable=True),
        sa.Column("project_scope_id", sa.Uuid(as_uuid=True), sa.ForeignKey("project_scopes.id"), nullable=True),
        sa.Column("origin_update_period_id", sa.Uuid(as_uuid=True), sa.ForeignKey("update_periods.id"), nullable=True),
        sa.Column("from_import_id", sa.Uuid(as_uuid=True), sa.ForeignKey("schedule_imports.id"), nullable=True),
        sa.Column("to_import_id", sa.Uuid(as_uuid=True), sa.ForeignKey("schedule_imports.id"), nullable=True),
        sa.Column("slip_days_at_creation", sa.Integer, nullable=True),
        sa.Column("slip_days_at_review", sa.Integer, nullable=True),
        sa.Column("status", _PLAN_STATUS, nullable=False, server_default="draft"),
        sa.Column("revision_no", sa.Integer, nullable=False, server_default="1"),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "activity_external_id", name="uq_recovery_plans_project_activity"),
    )
    op.create_index("ix_recovery_plans_tenant_id", "recovery_plans", ["tenant_id"])
    op.create_index("ix_recovery_plans_project_id", "recovery_plans", ["project_id"])

    op.create_table(
        "recovery_plan_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "recovery_plan_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("recovery_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("target_date", sa.Date, nullable=True),
        sa.Column("status", _ITEM_STATUS, nullable=False, server_default="open"),
        sa.Column("completed_at", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_recovery_plan_items_tenant_id", "recovery_plan_items", ["tenant_id"])
    op.create_index("ix_recovery_plan_items_project_id", "recovery_plan_items", ["project_id"])
    op.create_index("ix_recovery_plan_items_recovery_plan_id", "recovery_plan_items", ["recovery_plan_id"])
    op.create_index(
        "ix_recovery_plan_items_plan_order", "recovery_plan_items", ["recovery_plan_id", "order_index"]
    )

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
    op.drop_table("recovery_plan_items")
    op.drop_table("recovery_plans")
    _ITEM_STATUS.drop(op.get_bind(), checkfirst=True)
    _PLAN_STATUS.drop(op.get_bind(), checkfirst=True)
