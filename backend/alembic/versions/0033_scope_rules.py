"""Subcontractor scopes by rule; subcontractors lose company project roles.

project_scopes gains `wbs_ids` and `code_value_ids` (JSON lists of P6 ids):
the WBS subtrees / activity code values whose activities make up the scope
(services/scope_rules.py). Existing scopes get empty lists — no rule — and
keep whatever activities they had.

Data fix: a subcontractor's only permission is now Activity Status Updater
(update progress on their own scope) or nothing (view only). Project
Administrator, All Access, Execution and User Management are company roles —
User Management in particular let a subcontractor open the company's team
admin. A subcontractor who held any edit-capable role keeps the right to update
progress; anyone else becomes view only.

user_tenant_roles is under FORCE ROW LEVEL SECURITY, so the fix runs per
tenant with app.current_tenant_id set, as 0032 does.

Revision ID: 0033_scope_rules
Revises: 0032_clear_units_on_not_started
Create Date: 2026-10-07
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_scope_rules"
down_revision = "0032_clear_units_on_not_started"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")

STATUS_UPDATER = "activity_status_updater"
_EDIT_CAPABLE = {"project_administrator", "all_access", "execution", STATUS_UPDATER}


def subcontractor_roles(roles: list[str]) -> list[str]:
    return [STATUS_UPDATER] if set(roles) & _EDIT_CAPABLE else []


def upgrade() -> None:
    op.add_column("project_scopes", sa.Column("wbs_ids", _JSON, nullable=False, server_default="[]"))
    op.add_column("project_scopes", sa.Column("code_value_ids", _JSON, nullable=False, server_default="[]"))

    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        if postgres:
            bind.execute(
                sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
        rows = bind.execute(
            sa.text(
                "SELECT id, project_roles FROM user_tenant_roles "
                "WHERE tenant_id = :tenant_id AND role = 'subcontractor'"
            ),
            {"tenant_id": tenant_id},
        ).all()
        for row_id, raw in rows:
            roles = json.loads(raw) if isinstance(raw, str) else list(raw or [])
            fixed = subcontractor_roles(roles)
            if fixed != roles:
                bind.execute(
                    sa.text("UPDATE user_tenant_roles SET project_roles = :roles WHERE id = :id").bindparams(
                        sa.bindparam("roles", type_=_JSON)
                    ),
                    {"roles": fixed, "id": row_id},
                )


def downgrade() -> None:
    op.drop_column("project_scopes", "code_value_ids")
    op.drop_column("project_scopes", "wbs_ids")
