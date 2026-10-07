"""Which project roles a team member may be given, by whom — shared by the
invite (POST /invites) and edit (PATCH /team/{id}) paths so they can't drift."""

from fastapi import HTTPException, status

from app.deps import AuthContext
from app.models.user_tenant_role import (
    ADMIN_GRANTED_PROJECT_ROLES,
    COMPANY_PROJECT_ROLES,
    PROJECT_ROLE_LABELS,
    SUBCONTRACTOR_PROJECT_ROLES,
    ProjectRole,
    TenantRole,
)


def check_project_roles(role: TenantRole, project_roles: list[ProjectRole], actor: AuthContext) -> list[ProjectRole]:
    """Returns the roles de-duplicated in a stable order, or raises 400/403.

    - Subcontractors may only hold Activity Status Updater (or nothing: view
      only) — what they can see is set by their scopes, not by a company role.
    - Company employees need at least one company role (Update progress is
      the subcontractor one).
    - Only a company admin may hand out Project Manager, Planner and User
      Management (they import, set baselines or manage people): a User
      Management employee could otherwise mint peers with more reach.
    """
    roles = list(dict.fromkeys(project_roles))
    if role == TenantRole.subcontractor:
        if set(roles) - SUBCONTRACTOR_PROJECT_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A subcontractor can only be allowed to update progress on their own scope",
            )
        return roles
    if role == TenantRole.company_employee:
        if not roles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one role is required")
        if set(roles) - COMPANY_PROJECT_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Update progress is a subcontractor permission"
            )
        if actor.role != TenantRole.company_admin and set(roles) & ADMIN_GRANTED_PROJECT_ROLES:
            names = ", ".join(PROJECT_ROLE_LABELS[r] for r in ADMIN_GRANTED_PROJECT_ROLES & set(roles))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Only a company admin can grant {names}"
            )
        return roles
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company admins don't take project roles")
