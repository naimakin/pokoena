"""Menu-based project roles.

Old company roles -> new (models/user_tenant_role.ROLE_CAPABILITIES):

  project_administrator, all_access -> project_manager
  execution, activity_status_updater -> delivery_team
  user_management                    -> user_management (+ viewer when it was
                                        the only role: they could see every
                                        menu before, and keep that)
  nothing                            -> viewer

Subcontractor rows keep activity_status_updater (or nothing: view only);
company admins keep []. Runs over user_tenant_roles AND invites (a pending
invite's roles become the member's roles on acceptance). Both tables are under
FORCE ROW LEVEL SECURITY, so it runs per tenant with app.current_tenant_id
set, as 0032/0033 do. The app also reads legacy values itself
(parse_project_roles), so the deploy window before this runs is safe.

Revision ID: 0034_menu_roles
Revises: 0033_scope_rules
Create Date: 2026-10-07
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_menu_roles"
down_revision = "0033_scope_rules"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")

ORDER = ["project_manager", "planner", "delivery_team", "viewer", "dashboard_viewer", "user_management"]
_UP = {
    "project_administrator": "project_manager",
    "all_access": "project_manager",
    "execution": "delivery_team",
    "activity_status_updater": "delivery_team",
}
_DOWN = {
    "project_manager": "project_administrator",
    "planner": "project_administrator",
    "delivery_team": "execution",
    "viewer": "execution",
    "dashboard_viewer": "execution",
}


def map_roles(tenant_role: str, roles: list[str]) -> list[str]:
    if tenant_role == "company_admin":
        return []
    if tenant_role == "subcontractor":
        return ["activity_status_updater"] if "activity_status_updater" in roles else []
    mapped = {_UP.get(r, r) for r in roles} & set(ORDER)
    if not mapped - {"user_management"}:
        mapped.add("viewer")
    return [r for r in ORDER if r in mapped]


def unmap_roles(tenant_role: str, roles: list[str]) -> list[str]:
    if tenant_role != "company_employee":
        return roles
    return list(dict.fromkeys(_DOWN.get(r, r) for r in roles))


def _rewrite(fn) -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        if postgres:
            bind.execute(
                sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
        for table in ("user_tenant_roles", "invites"):
            rows = bind.execute(
                sa.text(f"SELECT id, role, project_roles FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).all()
            for row_id, role, raw in rows:
                roles = json.loads(raw) if isinstance(raw, str) else list(raw or [])
                fixed = fn(str(role), roles)
                if fixed != roles:
                    bind.execute(
                        sa.text(f"UPDATE {table} SET project_roles = :roles WHERE id = :id").bindparams(
                            sa.bindparam("roles", type_=_JSON)
                        ),
                        {"roles": fixed, "id": row_id},
                    )


def upgrade() -> None:
    _rewrite(map_roles)


def downgrade() -> None:
    _rewrite(unmap_roles)
