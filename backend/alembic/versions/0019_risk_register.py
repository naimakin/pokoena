"""Risk register: risk_items (register entry + mitigation-plan header) +
risk_action_items (itemised response actions).

Revision ID: 0019_risk_register
Revises: 0018_recovery_plans
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_risk_register"
down_revision = "0018_recovery_plans"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["risk_items", "risk_action_items"]

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")
_RISK_STATUS = sa.Enum("open", "mitigating", "closed", "occurred", name="risk_status")
_MIT_STATUS = sa.Enum("none", "draft", "submitted", "accepted", "needs_revision", name="mitigation_status")
_MIT_STRATEGY = sa.Enum("mitigate", "avoid", "transfer", "accept", name="mitigation_strategy")
_ACTION_STATUS = sa.Enum("open", "in_progress", "done", "dropped", name="risk_action_status")


def upgrade() -> None:
    op.create_table(
        "risk_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("cause", sa.Text, nullable=True),
        sa.Column("effect", sa.Text, nullable=True),
        sa.Column("category", sa.String(60), nullable=True),
        sa.Column("probability", sa.Integer, nullable=False, server_default="3"),
        sa.Column("impact", sa.Integer, nullable=False, server_default="3"),
        sa.Column("score", sa.Integer, nullable=False, server_default="9"),
        sa.Column("status", _RISK_STATUS, nullable=False, server_default="open"),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("wbs_path", sa.String(500), nullable=True),
        sa.Column("activity_external_ids", _JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("mitigation_strategy", _MIT_STRATEGY, nullable=True),
        sa.Column("mitigation_status", _MIT_STATUS, nullable=False, server_default="none"),
        sa.Column("mitigation_summary", sa.Text, nullable=True),
        sa.Column("revision_no", sa.Integer, nullable=False, server_default="1"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "code", name="uq_risk_items_project_code"),
    )
    op.create_index("ix_risk_items_tenant_id", "risk_items", ["tenant_id"])
    op.create_index("ix_risk_items_project_id", "risk_items", ["project_id"])

    op.create_table(
        "risk_action_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "risk_item_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("risk_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("target_date", sa.Date, nullable=True),
        sa.Column("status", _ACTION_STATUS, nullable=False, server_default="open"),
        sa.Column("completed_at", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_risk_action_items_tenant_id", "risk_action_items", ["tenant_id"])
    op.create_index("ix_risk_action_items_project_id", "risk_action_items", ["project_id"])
    op.create_index("ix_risk_action_items_risk_item_id", "risk_action_items", ["risk_item_id"])
    op.create_index(
        "ix_risk_action_items_risk_order", "risk_action_items", ["risk_item_id", "order_index"]
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
    op.drop_table("risk_action_items")
    op.drop_table("risk_items")
    for enum_type in (_ACTION_STATUS, _MIT_STRATEGY, _MIT_STATUS, _RISK_STATUS):
        enum_type.drop(op.get_bind(), checkfirst=True)
