"""project_role -> project_roles (a person can hold more than one)

Revision ID: 0004_multi_project_roles
Revises: 0003_password_resets
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_multi_project_roles"
down_revision = "0003_password_resets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB if is_postgres else sa.JSON

    for table in ("user_tenant_roles", "invites"):
        op.add_column(
            table, sa.Column("project_roles", json_type, nullable=False, server_default="[]")
        )
        if is_postgres:
            op.execute(
                f"UPDATE {table} SET project_roles = jsonb_build_array(project_role::text) "
                "WHERE project_role IS NOT NULL"
            )
        op.drop_column(table, "project_role")

    if is_postgres:
        sa.Enum(name="project_role").drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    project_role = postgresql.ENUM(
        "project_administrator",
        "all_access",
        "execution",
        "user_management",
        "activity_status_updater",
        name="project_role",
    )
    if is_postgres:
        project_role.create(bind, checkfirst=True)
    project_role_col = postgresql.ENUM(*project_role.enums, name="project_role", create_type=False)

    for table in ("user_tenant_roles", "invites"):
        op.add_column(table, sa.Column("project_role", project_role_col, nullable=True))
        if is_postgres:
            # Best-effort: only the first role survives a downgrade.
            op.execute(
                f"UPDATE {table} SET project_role = (project_roles->>0)::project_role "
                "WHERE jsonb_array_length(project_roles) > 0"
            )
        op.drop_column(table, "project_roles")
