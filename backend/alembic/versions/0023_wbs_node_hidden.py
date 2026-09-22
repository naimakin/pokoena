"""Let a stale WBS root be hidden from Planning > WBS without deleting it.

The wholesale-replace fix in 0022/xer_import.py only prunes what a NEW import
doesn't carry — a project whose two unrelated programs' WBS trees had already
accumulated live before that fix shipped stays mixed until its current update
is re-uploaded, and there's no stored record of which root belonged to which
import to clean it up automatically. This gives a human escape hatch: mark a
root wbs_node hidden, and its whole subtree drops out of the live tree
(GET .../wbs-nodes) while the underlying activities/rows are untouched.

Revision ID: 0023_wbs_node_hidden
Revises: 0022_wbs_snapshot
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_wbs_node_hidden"
down_revision = "0022_wbs_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wbs_nodes", sa.Column("is_hidden", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("wbs_nodes", "is_hidden")
