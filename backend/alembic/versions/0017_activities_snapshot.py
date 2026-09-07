"""Per-import activity snapshot (finish dates / criticality / status) on
schedule_imports — the basis for "vs previous UPD" slip detection.

Revision ID: 0017_activities_snapshot
Revises: 0016_saved_activity_filters
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_activities_snapshot"
down_revision = "0016_saved_activity_filters"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.add_column(
        "schedule_imports",
        sa.Column("activities_snapshot", _JSON, nullable=False, server_default=sa.text("'[]'")),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Backfill the latest import per project from the live activities table —
        # a plain column copy (the live rows ARE that import's result), so the
        # feature is only "one import dark" instead of two.
        op.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (project_id) id, project_id
                  FROM schedule_imports
                 ORDER BY project_id, imported_at DESC
            ),
            snap AS (
                SELECT l.id AS import_id,
                       jsonb_agg(jsonb_build_object(
                           'external_id', a.external_id,
                           'p6_task_id', a.p6_task_id,
                           'name', a.name,
                           'wbs_path', a.wbs_path,
                           'planned_finish', to_char(a.planned_finish, 'YYYY-MM-DD'),
                           'early_finish', to_char(a.early_finish, 'YYYY-MM-DD'),
                           'actual_finish', to_char(a.actual_finish, 'YYYY-MM-DD'),
                           'is_critical', a.is_critical,
                           'is_longest_path', a.is_longest_path,
                           'total_float_hours', a.total_float_hours,
                           'status', a.status,
                           'percent_complete', a.percent_complete
                       )) AS payload
                  FROM latest l
                  JOIN activities a ON a.project_id = l.project_id
                 GROUP BY l.id
            )
            UPDATE schedule_imports si
               SET activities_snapshot = snap.payload
              FROM snap
             WHERE si.id = snap.import_id
            """
        )


def downgrade() -> None:
    op.drop_column("schedule_imports", "activities_snapshot")
