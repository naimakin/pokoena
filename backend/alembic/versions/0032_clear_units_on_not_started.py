"""Data fix: a Not Started activity has no actual resource units.

P6 never writes actual units (TASKRSRC.act_reg_qty) on an activity that hasn't
started, and Poko's current progress rules can't produce that state either
(services/activity_progress.py: units = budget x %, and Not Started is 0 %).
Rows written by an earlier version of the import/progress code could still
carry it — e.g. HER01-DES-MS-1070: Not Started, 0 %, yet 408 actual / 0
remaining on its labor assignment, which the export would then send to P6.

This puts those assignments back to 0 actual / full budget remaining. It
touches nothing else: in-progress and finished activities keep their units,
including the ones whose units legitimately differ from the % (P6 data).

resource_assignments is under FORCE ROW LEVEL SECURITY, which applies to the
table owner running migrations too — with no tenant context an UPDATE would
silently match nothing. So it runs per tenant, setting app.current_tenant_id
for each, exactly as the app does (db/session.py::set_rls_context).

Data-only: no schema change, and there is nothing to restore on downgrade.

Revision ID: 0032_clear_units_on_not_started
Revises: 0031_my_desk
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_clear_units_on_not_started"
down_revision = "0031_my_desk"
branch_labels = None
depends_on = None

# Portable (no UPDATE ... FROM) so the test suite can run it on SQLite.
FIX_SQL = sa.text(
    """
    UPDATE resource_assignments
       SET act_reg_qty = 0,
           remain_qty = target_qty
     WHERE tenant_id = :tenant_id
       AND act_reg_qty > 0
       AND activity_id IN (
             SELECT id FROM activities
              WHERE tenant_id = :tenant_id
                AND status = 'not_started'
           )
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        if postgres:
            bind.execute(
                sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
        bind.execute(FIX_SQL, {"tenant_id": tenant_id})


def downgrade() -> None:
    pass
