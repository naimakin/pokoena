"""initial multi-tenant schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# Tenant-scoped tables get RLS enabled + a tenant-isolation policy. `users`,
# `user_identities`, and `tenants` are deliberately excluded — they have no
# tenant_id column (users/identities are global; tenants is the registry itself).
TENANT_SCOPED_TABLES = [
    "subcontractor_organizations",
    "user_tenant_roles",
    "projects",
    "project_scopes",
    "project_memberships",
    "subcontractor_scope_assignments",
    "activities",
    "activity_relationships",
    "update_periods",
    "change_requests",
    "scope_submissions",
    "invites",
    "audit_logs",
]


def upgrade() -> None:
    bind = op.get_bind()

    # ---- enum types (created once, referenced with create_type=False below) ----
    tenant_status = postgresql.ENUM("active", "suspended", "deleted", name="tenant_status")
    identity_provider = postgresql.ENUM("password", "google", "microsoft_entra", name="identity_provider")
    tenant_role = postgresql.ENUM(
        "company_admin", "company_employee", "subcontractor", name="tenant_role"
    )
    project_permission = postgresql.ENUM("view", "edit", name="project_permission")
    activity_status = postgresql.ENUM("not_started", "in_progress", "complete", name="activity_status")
    link_type = postgresql.ENUM("FS", "SS", "FF", "SF", name="link_type")
    update_period_status = postgresql.ENUM("open", "closed", name="update_period_status")
    risk_level = postgresql.ENUM("low", "medium", "high", name="risk_level")
    change_request_status = postgresql.ENUM(
        "pending", "approved", "rejected", name="change_request_status"
    )
    invite_status = postgresql.ENUM("pending", "accepted", "expired", "revoked", name="invite_status")

    for enum_type in (
        tenant_status,
        identity_provider,
        tenant_role,
        project_permission,
        activity_status,
        link_type,
        update_period_status,
        risk_level,
        change_request_status,
        invite_status,
    ):
        enum_type.create(bind, checkfirst=True)

    def no_create(enum_type: postgresql.ENUM) -> postgresql.ENUM:
        return postgresql.ENUM(*enum_type.enums, name=enum_type.name, create_type=False)

    # ---- tables ----
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("status", no_create(tenant_status), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", no_create(identity_provider), nullable=False),
        sa.Column("provider_subject_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "provider_subject_id", name="uq_user_identity_provider_subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])

    op.create_table(
        "subcontractor_organizations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discipline", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_subcontractor_organizations_tenant_id", "subcontractor_organizations", ["tenant_id"]
    )

    op.create_table(
        "user_tenant_roles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("role", no_create(tenant_role), nullable=False),
        sa.Column(
            "subcontractor_org_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subcontractor_organizations.id"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant_roles_user_tenant"),
    )
    op.create_index("ix_user_tenant_roles_user_id", "user_tenant_roles", ["user_id"])
    op.create_index("ix_user_tenant_roles_tenant_id", "user_tenant_roles", ["tenant_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_projects_tenant_code"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])

    op.create_table(
        "project_scopes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "subcontractor_org_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subcontractor_organizations.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discipline", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_project_scopes_tenant_id", "project_scopes", ["tenant_id"])
    op.create_index("ix_project_scopes_project_id", "project_scopes", ["project_id"])
    op.create_index("ix_project_scopes_subcontractor_org_id", "project_scopes", ["subcontractor_org_id"])

    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("permission", no_create(project_permission), nullable=False, server_default="view"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_memberships_project_user"),
    )
    op.create_index("ix_project_memberships_tenant_id", "project_memberships", ["tenant_id"])
    op.create_index("ix_project_memberships_project_id", "project_memberships", ["project_id"])
    op.create_index("ix_project_memberships_user_id", "project_memberships", ["user_id"])

    op.create_table(
        "subcontractor_scope_assignments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "project_scope_id", sa.Uuid(as_uuid=True), sa.ForeignKey("project_scopes.id"), nullable=False
        ),
        sa.Column("assigned_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "project_scope_id", name="uq_sub_scope_assignment_user_scope"),
    )
    op.create_index(
        "ix_subcontractor_scope_assignments_tenant_id", "subcontractor_scope_assignments", ["tenant_id"]
    )
    op.create_index(
        "ix_subcontractor_scope_assignments_user_id", "subcontractor_scope_assignments", ["user_id"]
    )
    op.create_index(
        "ix_subcontractor_scope_assignments_project_scope_id",
        "subcontractor_scope_assignments",
        ["project_scope_id"],
    )

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "project_scope_id", sa.Uuid(as_uuid=True), sa.ForeignKey("project_scopes.id"), nullable=True
        ),
        sa.Column("external_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discipline", sa.String(120), nullable=False),
        sa.Column("planned_start", sa.Date, nullable=True),
        sa.Column("planned_finish", sa.Date, nullable=True),
        sa.Column("actual_start", sa.Date, nullable=True),
        sa.Column("actual_finish", sa.Date, nullable=True),
        sa.Column("percent_complete", sa.Integer, nullable=False, server_default="0"),
        sa.Column("remaining_duration_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", no_create(activity_status), nullable=False, server_default="not_started"),
    )
    op.create_index("ix_activities_tenant_id", "activities", ["tenant_id"])
    op.create_index("ix_activities_project_id", "activities", ["project_id"])
    op.create_index("ix_activities_project_scope_id", "activities", ["project_scope_id"])

    op.create_table(
        "activity_relationships",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("predecessor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("successor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("link_type", no_create(link_type), nullable=False, server_default="FS"),
        sa.Column("lag_days", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_activity_relationships_tenant_id", "activity_relationships", ["tenant_id"])

    op.create_table(
        "update_periods",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("period_number", sa.Integer, nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", no_create(update_period_status), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_update_periods_tenant_id", "update_periods", ["tenant_id"])

    op.create_table(
        "change_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
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
        sa.Column("risk_level", no_create(risk_level), nullable=False, server_default="medium"),
        sa.Column(
            "status", no_create(change_request_status), nullable=False, server_default="pending"
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_change_requests_tenant_id", "change_requests", ["tenant_id"])
    op.create_index("ix_change_requests_update_period_id", "change_requests", ["update_period_id"])

    op.create_table(
        "scope_submissions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "update_period_id", sa.Uuid(as_uuid=True), sa.ForeignKey("update_periods.id"), nullable=False
        ),
        sa.Column(
            "subcontractor_org_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subcontractor_organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "update_period_id", "subcontractor_org_id", name="uq_scope_submission_period_org"
        ),
    )
    op.create_index("ix_scope_submissions_tenant_id", "scope_submissions", ["tenant_id"])
    op.create_index("ix_scope_submissions_update_period_id", "scope_submissions", ["update_period_id"])

    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", no_create(tenant_role), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", no_create(invite_status), nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("token_hash", name="uq_invites_token_hash"),
    )
    op.create_index("ix_invites_tenant_id", "invites", ["tenant_id"])
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_token_hash", "invites", ["token_hash"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target_type", sa.String(120), nullable=True),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    # ---- row-level security ----
    # `poko_app`/`poko_bypass` (the RLS-bound and BYPASSRLS roles referenced by
    # the policies below) are deliberately NOT created here with CREATE ROLE:
    # that's a cluster-wide superuser-only operation that a managed Postgres
    # app-level user (this migration's own role, in production) typically can't
    # perform. Local dev creates them via postgres-init/01_rls_roles.sql (run
    # automatically by the docker-compose postgres service on first init);
    # production creates them once via the hosting provider's control panel,
    # per infra/README.md. This migration only touches the tables it owns.
    for table_name in TENANT_SCOPED_TABLES:
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
    for table_name in reversed(TENANT_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")

    op.drop_table("audit_logs")
    op.drop_table("invites")
    op.drop_table("scope_submissions")
    op.drop_table("change_requests")
    op.drop_table("update_periods")
    op.drop_table("activity_relationships")
    op.drop_table("activities")
    op.drop_table("subcontractor_scope_assignments")
    op.drop_table("project_memberships")
    op.drop_table("project_scopes")
    op.drop_table("projects")
    op.drop_table("user_tenant_roles")
    op.drop_table("subcontractor_organizations")
    op.drop_table("user_identities")
    op.drop_table("users")
    op.drop_table("tenants")

    bind = op.get_bind()
    for enum_name in (
        "invite_status",
        "change_request_status",
        "risk_level",
        "update_period_status",
        "link_type",
        "activity_status",
        "project_permission",
        "tenant_role",
        "identity_provider",
        "tenant_status",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
