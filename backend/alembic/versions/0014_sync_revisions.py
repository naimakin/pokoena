"""Export / Sync to P6 revision labels: schedule_exports (EXP-n) + revision
columns on schedule_imports (UPD-n), plus optional round-trip linkage.

Revision ID: 0014_sync_revisions
Revises: 0013_baseline_resources
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_sync_revisions"
down_revision = "0013_baseline_resources"
branch_labels = None
depends_on = None

NEW_TENANT_SCOPED_TABLES = ["schedule_exports"]


def upgrade() -> None:
    op.create_table(
        "schedule_exports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("revision_no", sa.Integer, nullable=False),
        sa.Column("revision_label", sa.String(30), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("data_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activity_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("exported_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "revision_no", name="uq_schedule_exports_project_revision_no"),
    )
    op.create_index("ix_schedule_exports_tenant_id", "schedule_exports", ["tenant_id"])
    op.create_index("ix_schedule_exports_project_id", "schedule_exports", ["project_id"])

    op.add_column("schedule_imports", sa.Column("revision_no", sa.Integer, nullable=True))
    op.add_column("schedule_imports", sa.Column("revision_label", sa.String(30), nullable=True))
    op.add_column(
        "schedule_imports",
        sa.Column(
            "roundtrip_from_export_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("schedule_exports.id"),
            nullable=True,
        ),
    )

    for table_name in NEW_TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table_name}
                FOR ALL
                USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
                WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            """
        )

    # Backfill existing history so the sync log reads consistently: the import
    # each baseline points at is the "Baseline programme" (unnumbered); every
    # other import gets a per-project UPD-n by import order.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE schedule_imports si
               SET revision_label = 'Baseline programme'
             WHERE EXISTS (SELECT 1 FROM baselines b WHERE b.schedule_import_id = si.id)
            """
        )
        op.execute(
            """
            WITH ranked AS (
                SELECT si.id,
                       ROW_NUMBER() OVER (
                           PARTITION BY si.project_id ORDER BY si.imported_at, si.id
                       ) AS rn
                  FROM schedule_imports si
                 WHERE NOT EXISTS (
                       SELECT 1 FROM baselines b WHERE b.schedule_import_id = si.id
                 )
            )
            UPDATE schedule_imports si
               SET revision_no = ranked.rn,
                   revision_label = 'UPD-' || ranked.rn
              FROM ranked
             WHERE ranked.id = si.id
            """
        )


def downgrade() -> None:
    op.drop_column("schedule_imports", "roundtrip_from_export_id")
    op.drop_column("schedule_imports", "revision_label")
    op.drop_column("schedule_imports", "revision_no")

    for table_name in reversed(NEW_TENANT_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.drop_table("schedule_exports")
