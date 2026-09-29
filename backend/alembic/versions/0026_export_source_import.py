"""Export / Sync to P6: which programme an export was built from.

`schedule_exports.source_import_id` records the ScheduleImport whose .xer the
export was produced from — the export page now lets the user pick a programme
instead of always taking the current update, so the sync log has to say which
one went out ("EXP-3 · from UPD-1"). NULL on exports made before this migration
and on a project that has no imports at all.

Revision ID: 0026_export_source_import
Revises: 0025_report_formats
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_export_source_import"
down_revision = "0025_report_formats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_exports",
        sa.Column(
            "source_import_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("schedule_imports.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_exports", "source_import_id")
