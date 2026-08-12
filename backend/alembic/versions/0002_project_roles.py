"""project roles, user contact fields, invite details

Revision ID: 0002_project_roles
Revises: 0001_initial
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_project_roles"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    project_role = postgresql.ENUM(
        "project_administrator",
        "all_access",
        "execution",
        "user_management",
        "activity_status_updater",
        name="project_role",
    )
    project_role.create(bind, checkfirst=True)
    project_role_col = postgresql.ENUM(*project_role.enums, name="project_role", create_type=False)

    op.add_column("users", sa.Column("title", sa.String(150), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(50), nullable=True))

    op.add_column("user_tenant_roles", sa.Column("project_role", project_role_col, nullable=True))

    op.add_column(
        "invites", sa.Column("full_name", sa.String(255), nullable=False, server_default="")
    )
    op.add_column("invites", sa.Column("title", sa.String(150), nullable=True))
    op.add_column("invites", sa.Column("phone", sa.String(50), nullable=True))
    op.add_column("invites", sa.Column("project_role", project_role_col, nullable=True))

    op.drop_column("project_memberships", "permission")

    sa.Enum(name="project_permission").drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()

    project_permission = postgresql.ENUM("view", "edit", name="project_permission")
    project_permission.create(bind, checkfirst=True)
    op.add_column(
        "project_memberships",
        sa.Column(
            "permission",
            postgresql.ENUM(*project_permission.enums, name="project_permission", create_type=False),
            nullable=False,
            server_default="view",
        ),
    )

    op.drop_column("invites", "project_role")
    op.drop_column("invites", "phone")
    op.drop_column("invites", "title")
    op.drop_column("invites", "full_name")

    op.drop_column("user_tenant_roles", "project_role")

    op.drop_column("users", "phone")
    op.drop_column("users", "title")

    sa.Enum(name="project_role").drop(bind, checkfirst=True)
