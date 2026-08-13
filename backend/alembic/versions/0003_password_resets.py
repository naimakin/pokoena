"""password reset tokens

Revision ID: 0003_password_resets
Revises: 0002_project_roles
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_password_resets"
down_revision = "0002_project_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No RLS — same as `users`/`user_identities`: a reset targets one global
    # identity, not tenant-scoped business data.
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("token_hash", name="uq_password_resets_token_hash"),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])
    op.create_index("ix_password_resets_token_hash", "password_resets", ["token_hash"])


def downgrade() -> None:
    op.drop_table("password_resets")
