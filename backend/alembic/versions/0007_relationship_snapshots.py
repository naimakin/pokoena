"""Logic Diff support: frozen relationship snapshot per schedule import

Revision ID: 0007_relationship_snapshots
Revises: 0006_dcma_fields
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_relationship_snapshots"
down_revision = "0006_dcma_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB if is_postgres else sa.JSON

    op.add_column(
        "schedule_imports", sa.Column("relationships_snapshot", json_type, nullable=False, server_default="[]")
    )


def downgrade() -> None:
    op.drop_column("schedule_imports", "relationships_snapshot")
