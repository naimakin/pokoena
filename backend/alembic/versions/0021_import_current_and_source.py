"""Program Library: "Current update" selection + stored source .xer.

`schedule_imports.is_current` marks the import that is the project's live
schedule (previously implicit: the newest by imported_at). `source_file` keeps a
gzipped copy of each upload's .xer so the live tables can be rebuilt exactly from
an earlier import when the user re-points "Current update" at it; imports made
before this migration have no file (`has_source_file` false) and can't be chosen.

Revision ID: 0021_import_current_and_source
Revises: 0020_clear_critical_on_finished
Create Date: 2026-09-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_import_current_and_source"
down_revision = "0020_clear_critical_on_finished"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedule_imports", sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column(
        "schedule_imports", sa.Column("has_source_file", sa.Boolean, nullable=False, server_default=sa.false())
    )
    op.add_column("schedule_imports", sa.Column("source_file", sa.LargeBinary, nullable=True))

    # Today's implicit rule: the newest import per project is the live schedule.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE schedule_imports
               SET is_current = true
             WHERE id IN (
                   SELECT DISTINCT ON (project_id) id
                     FROM schedule_imports
                    ORDER BY project_id, imported_at DESC
             )
            """
        )


def downgrade() -> None:
    op.drop_column("schedule_imports", "source_file")
    op.drop_column("schedule_imports", "has_source_file")
    op.drop_column("schedule_imports", "is_current")
