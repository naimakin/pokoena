"""DCMA 14-point check support: secondary constraint + longest-path flag

Revision ID: 0006_dcma_fields
Revises: 0005_p6_schedule_import
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_dcma_fields"
down_revision = "0005_p6_schedule_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("constraint_type_2", sa.String(30), nullable=True))
    op.add_column("activities", sa.Column("constraint_date_2", sa.Date, nullable=True))
    op.add_column(
        "activities", sa.Column("is_longest_path", sa.Boolean, nullable=False, server_default="false")
    )


def downgrade() -> None:
    op.drop_column("activities", "is_longest_path")
    op.drop_column("activities", "constraint_date_2")
    op.drop_column("activities", "constraint_type_2")
