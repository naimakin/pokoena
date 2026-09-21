"""Data fix: finished activities must not be flagged critical.

`activities.is_critical` is recomputed from the .xer on every import, and the
importer now excludes anything with an actual finish (or TK_Complete). Rows
imported before that rule still carry the stale flag until their next upload —
this clears it in place so completed work stops showing up as "Critical" in
Program Library / Baselines / Schedule / Gantt without waiting for a re-import.

Data-only: no schema change, and there is nothing to restore on downgrade.

Revision ID: 0020_clear_critical_on_finished
Revises: 0019_risk_register
Create Date: 2026-09-21
"""

from alembic import op

revision = "0020_clear_critical_on_finished"
down_revision = "0019_risk_register"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE activities
           SET is_critical = false
         WHERE is_critical
           AND (actual_finish IS NOT NULL OR percent_complete >= 100)
        """
    )


def downgrade() -> None:
    pass
