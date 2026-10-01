"""P6 physical % complete as its own column + per-activity site/supply risk.

`percent_complete` becomes the % Poko SHOWS, derived the way the planning team
specified (services/activity_progress.py::display_percent): units % from the
RT_Labor assignments when the activity has any, otherwise 100 / 0 for
completed / not-started work and the duration % for work in progress. That is
no longer always P6's TASK.phys_complete_pct, so the physical % gets its own
column — imported from the .xer, written by a % entry on an activity without
labor resources, and exported back to the same TASK column. Backfilled from
`percent_complete`, which is what the export wrote to phys_complete_pct until
now, so the next export of an untouched project is byte-for-byte unchanged.

`percent_complete` itself is not recomputed here: Poko-entered % on an
activity without resources never moved its remaining hours, so re-deriving the
duration % now would wipe that entry. The new rule takes over per activity on
its next import or progress edit.

`site_risk` (high / standard / low, null = not assessed) is the one input of
the activity Criticality Score that P6 doesn't carry — see
services/criticality.py. A team annotation, like `is_important`: .xer import
never touches it.

Revision ID: 0028_progress_pct_and_site_risk
Revises: 0027_qsra
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_progress_pct_and_site_risk"
down_revision = "0027_qsra"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("phys_complete_pct", sa.Float, nullable=True))
    op.add_column("activities", sa.Column("site_risk", sa.String(20), nullable=True))
    op.execute("UPDATE activities SET phys_complete_pct = percent_complete")


def downgrade() -> None:
    op.drop_column("activities", "site_risk")
    op.drop_column("activities", "phys_complete_pct")
