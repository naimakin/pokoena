"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discipline", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("code", name="uq_projects_code"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "subcontractor", "viewer", name="user_role"),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("company_id", sa.Uuid(as_uuid=True), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "update_periods",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("period_number", sa.Integer, nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "closed", name="update_period_status"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("external_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discipline", sa.String(120), nullable=False),
        sa.Column("planned_start", sa.Date, nullable=True),
        sa.Column("planned_finish", sa.Date, nullable=True),
        sa.Column("actual_start", sa.Date, nullable=True),
        sa.Column("actual_finish", sa.Date, nullable=True),
        sa.Column("percent_complete", sa.Integer, nullable=False, server_default="0"),
        sa.Column("remaining_duration_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("not_started", "in_progress", "complete", name="activity_status"),
            nullable=False,
            server_default="not_started",
        ),
    )
    op.create_index("ix_activities_project_id", "activities", ["project_id"])
    op.create_index("ix_activities_company_id", "activities", ["company_id"])

    op.create_table(
        "activity_relationships",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("predecessor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("successor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column(
            "link_type",
            sa.Enum("FS", "SS", "FF", "SF", name="link_type"),
            nullable=False,
            server_default="FS",
        ),
        sa.Column("lag_days", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "change_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "update_period_id", sa.Uuid(as_uuid=True), sa.ForeignKey("update_periods.id"), nullable=False
        ),
        sa.Column(
            "activity_relationship_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("activity_relationships.id"),
            nullable=True,
        ),
        sa.Column("activity_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=True),
        sa.Column(
            "requested_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("field_changed", sa.String(120), nullable=False),
        sa.Column("before_value", sa.String(255), nullable=False),
        sa.Column("after_value", sa.String(255), nullable=False),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("low", "medium", "high", name="risk_level"),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="change_request_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_change_requests_update_period_id", "change_requests", ["update_period_id"])

    op.create_table(
        "scope_submissions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "update_period_id", sa.Uuid(as_uuid=True), sa.ForeignKey("update_periods.id"), nullable=False
        ),
        sa.Column("company_id", sa.Uuid(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "submitted_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("update_period_id", "company_id", name="uq_scope_submission_period_company"),
    )
    op.create_index("ix_scope_submissions_update_period_id", "scope_submissions", ["update_period_id"])


def downgrade() -> None:
    op.drop_table("scope_submissions")
    op.drop_table("change_requests")
    op.drop_table("activity_relationships")
    op.drop_table("activities")
    op.drop_table("update_periods")
    op.drop_table("users")
    op.drop_table("projects")
    op.drop_table("companies")

    bind = op.get_bind()
    for enum_name in (
        "risk_level",
        "change_request_status",
        "link_type",
        "activity_status",
        "update_period_status",
        "user_role",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
