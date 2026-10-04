"""My Desk: activity pins and personal notes.

activity_pins — activities one user pinned to their own desk, keyed on the P6
activity ID (re-linked on rename like recovery_plans), with the finish / total
float frozen at pin time for "drift since pinned".

personal_notes — private notes and reminders, optionally on a project and an
activity. Both tables are tenant-isolated by RLS; privacy between users of the
same tenant is the application's `user_id` filter (as saved_activity_filters).

Revision ID: 0031_my_desk
Revises: 0030_project_dcma_thresholds
Create Date: 2026-10-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_my_desk"
down_revision = "0030_project_dcma_thresholds"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["activity_pins", "personal_notes"]

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "activity_pins",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("activity_external_id", sa.String(50), nullable=False),
        sa.Column("activity_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("pinned_finish", sa.Date, nullable=True),
        sa.Column("pinned_total_float_hours", sa.Float, nullable=True),
        sa.Column("pinned_hours_per_day", sa.Float, nullable=True),
        sa.Column("pinned_revision_label", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "user_id", "project_id", "activity_external_id", name="uq_activity_pins_user_project_activity"
        ),
    )
    op.create_index("ix_activity_pins_tenant_id", "activity_pins", ["tenant_id"])
    op.create_index("ix_activity_pins_project_id", "activity_pins", ["project_id"])
    op.create_index("ix_activity_pins_user_id", "activity_pins", ["user_id"])

    op.create_table(
        "personal_notes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("activity_external_id", sa.String(50), nullable=True),
        sa.Column("activity_name", sa.String(255), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("remind_on", sa.Date, nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context", _JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_personal_notes_tenant_id", "personal_notes", ["tenant_id"])
    op.create_index("ix_personal_notes_user_id", "personal_notes", ["user_id"])
    op.create_index("ix_personal_notes_project_id", "personal_notes", ["project_id"])

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
    op.drop_table("personal_notes")
    op.drop_table("activity_pins")
