"""DCMA 14-Point: a project's own targets.

projects.dcma_thresholds holds the targets a project sets for itself over
DCMA's defaults (engine/quality/dcma.py::DcmaThresholds), only the ones that
differ. Null means DCMA's own targets throughout. projects is already under
row-level security, so nothing to add there.

Revision ID: 0030_project_dcma_thresholds
Revises: 0029_schedule_simulations
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_project_dcma_thresholds"
down_revision = "0029_schedule_simulations"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.add_column("projects", sa.Column("dcma_thresholds", _JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "dcma_thresholds")
