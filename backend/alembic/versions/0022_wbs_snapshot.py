"""Per-import WBS snapshot, and stop accumulating stale WBS trees.

`wbs_nodes` was only ever upserted, never pruned, so a project that had two
unrelated .xer files uploaded to it (or a P6 project whose root WBS id changed
across revisions) kept BOTH programs' WBS trees forever, shown side by side on
Planning -> WBS with no way to tell which was current. `wbs_nodes` is now
wholesale-replaced per import (like activity_relationships already is) so it
always matches only the current update; `schedule_imports.wbs_snapshot` freezes
each import's WBS structure so an earlier program's tree can still be viewed on
request (see api/routes/schedule_imports.py's new /{id}/wbs-nodes endpoint).

Revision ID: 0022_wbs_snapshot
Revises: 0021_import_current_and_source
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_wbs_snapshot"
down_revision = "0021_import_current_and_source"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.add_column("schedule_imports", sa.Column("wbs_snapshot", _JSON, nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    op.drop_column("schedule_imports", "wbs_snapshot")
