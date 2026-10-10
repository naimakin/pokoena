"""Indexes the models declared but no migration ever created.

- activity_relationships.project_id — every per-project relationship read
  (DCMA, Float Path, criticality's successor counts, logic checks) filtered a
  table holding every project's links without an index.
- activity_relationships.predecessor_id / successor_id — the activity panel's
  predecessors / successors lookup, and the FK checks when an activity row is
  deleted (Postgres never indexes the referencing side of a foreign key).
- update_periods.project_id — the Dashboard's period lookup.

IF NOT EXISTS: harmless on a database where one was added by hand.

Revision ID: 0037_perf_indexes
Revises: 0036_recovery_edits
Create Date: 2026-10-10
"""

from alembic import op

revision = "0037_perf_indexes"
down_revision = "0036_recovery_edits"
branch_labels = None
depends_on = None

_INDEXES = [
    ("ix_activity_relationships_project_id", "activity_relationships", "project_id"),
    ("ix_activity_relationships_predecessor_id", "activity_relationships", "predecessor_id"),
    ("ix_activity_relationships_successor_id", "activity_relationships", "successor_id"),
    ("ix_update_periods_project_id", "update_periods", "project_id"),
]


def upgrade() -> None:
    for name, table, column in _INDEXES:
        op.create_index(name, table, [column], if_not_exists=True)


def downgrade() -> None:
    for name, table, _column in reversed(_INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
