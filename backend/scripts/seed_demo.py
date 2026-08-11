"""Seeds a demo tenant so the three Phase 1 screens have real data to render.

Usage (from backend/): python -m scripts.seed_demo

Idempotent: re-running skips creation if the tenant slug already exists.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.session import SessionLocal, set_rls_context
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.change_request import ChangeRequest, ChangeRequestStatus, RiskLevel
from app.models.project import Project
from app.models.project_membership import ProjectMembership, ProjectPermission
from app.models.project_scope import ProjectScope
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.tenant import Tenant, TenantStatus
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole

TENANT_SLUG = "riverside-logistics"
PROJECT_CODE = "RLP-P2"


def main() -> None:
    db = SessionLocal()
    try:
        if db.query(Tenant).filter(Tenant.slug == TENANT_SLUG).first():
            print(f"Tenant {TENANT_SLUG} already seeded — skipping.")
            return

        tenant = Tenant(
            id=uuid.uuid4(),
            name="Riverside Logistics Park GC",
            slug=TENANT_SLUG,
            status=TenantStatus.active,
        )
        db.add(tenant)
        db.flush()

        # Every insert below needs this tenant's RLS context set — this script
        # uses the same RLS-bound poko_app connection a real request would, it
        # just isn't going through a FastAPI dependency to get the context set.
        set_rls_context(db, tenant.id)

        project = Project(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Riverside Logistics Park — Phase 2",
            code=PROJECT_CODE,
        )
        db.add(project)

        structural_org = SubcontractorOrganization(
            id=uuid.uuid4(), tenant_id=tenant.id, name="Structural Concrete Co.", discipline="Structural"
        )
        mep_org = SubcontractorOrganization(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="MEP Systems Inc.",
            discipline="Mechanical/Electrical/Plumbing",
        )
        steel_org = SubcontractorOrganization(
            id=uuid.uuid4(), tenant_id=tenant.id, name="Steel Erectors LLC", discipline="Structural Steel"
        )
        db.add_all([structural_org, mep_org, steel_org])

        admin_user = User(
            id=uuid.uuid4(),
            email="admin@pokoena.com",
            hashed_password=hash_password("ChangeMe123!"),
            full_name="Jordan Diaz",
            is_active=True,
        )
        employee_user = User(
            id=uuid.uuid4(),
            email="employee@pokoena.com",
            hashed_password=hash_password("ChangeMe123!"),
            full_name="Sam Rivera",
            is_active=True,
        )
        sub_user = User(
            id=uuid.uuid4(),
            email="mep@pokoena.com",
            hashed_password=hash_password("ChangeMe123!"),
            full_name="Riley Kim",
            is_active=True,
        )
        db.add_all([admin_user, employee_user, sub_user])

        # Flush every parent row (project/orgs/users) before anything that
        # references them by foreign key: none of these models declare an ORM
        # relationship() to each other (kept deliberately plain-column, see the
        # models), so the unit-of-work has no dependency graph to auto-order
        # inserts by — without this, dependents can get flushed before their
        # own parent row exists and the FK constraint rejects them.
        db.flush()

        db.add_all(
            [
                UserTenantRole(
                    id=uuid.uuid4(),
                    user_id=admin_user.id,
                    tenant_id=tenant.id,
                    role=TenantRole.company_admin,
                    is_active=True,
                ),
                UserTenantRole(
                    id=uuid.uuid4(),
                    user_id=employee_user.id,
                    tenant_id=tenant.id,
                    role=TenantRole.company_employee,
                    is_active=True,
                ),
                UserTenantRole(
                    id=uuid.uuid4(),
                    user_id=sub_user.id,
                    tenant_id=tenant.id,
                    role=TenantRole.subcontractor,
                    subcontractor_org_id=mep_org.id,
                    is_active=True,
                ),
            ]
        )
        db.add(
            ProjectMembership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                project_id=project.id,
                user_id=employee_user.id,
                permission=ProjectPermission.edit,
            )
        )

        period = UpdatePeriod(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            period_number=14,
            label="Period 14",
            opens_at=datetime.now(timezone.utc) - timedelta(days=13),
            deadline_at=datetime.now(timezone.utc) + timedelta(days=3),
            status=UpdatePeriodStatus.open,
        )
        db.add(period)

        mep_scope = ProjectScope(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            subcontractor_org_id=mep_org.id,
            name="MEP",
            discipline="MEP",
        )
        structural_scope = ProjectScope(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            subcontractor_org_id=structural_org.id,
            name="Structural",
            discipline="Structural",
        )
        steel_scope = ProjectScope(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            subcontractor_org_id=steel_org.id,
            name="Structural Steel",
            discipline="Structural Steel",
        )
        db.add_all([mep_scope, structural_scope, steel_scope])
        db.flush()

        db.add(
            SubcontractorScopeAssignment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=sub_user.id,
                project_scope_id=mep_scope.id,
                assigned_by_user_id=admin_user.id,
            )
        )

        activities = [
            Activity(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                project_id=project.id,
                project_scope_id=mep_scope.id,
                external_id="MEP-2201",
                name="Chilled Water Piping – Level 1",
                discipline="MEP",
                planned_start=date(2026, 5, 12),
                planned_finish=date(2026, 7, 22),
                actual_start=date(2026, 5, 12),
                actual_finish=date(2026, 7, 22),
                percent_complete=100,
                remaining_duration_days=0,
                status=ActivityStatus.complete,
            ),
            Activity(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                project_id=project.id,
                project_scope_id=mep_scope.id,
                external_id="MEP-2205",
                name="Electrical Rough-in – Level 2",
                discipline="MEP",
                planned_start=date(2026, 7, 14),
                planned_finish=date(2026, 8, 28),
                actual_start=date(2026, 7, 14),
                percent_complete=65,
                remaining_duration_days=9,
                status=ActivityStatus.in_progress,
            ),
            Activity(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                project_id=project.id,
                project_scope_id=mep_scope.id,
                external_id="MEP-2210",
                name="Chiller Plant Rough-in",
                discipline="MEP",
                planned_start=date(2026, 7, 28),
                planned_finish=date(2026, 9, 4),
                actual_start=date(2026, 7, 28),
                percent_complete=30,
                remaining_duration_days=14,
                status=ActivityStatus.in_progress,
            ),
            Activity(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                project_id=project.id,
                project_scope_id=mep_scope.id,
                external_id="MEP-2214",
                name="Ductwork – Level 3",
                discipline="MEP",
                planned_start=date(2026, 8, 18),
                planned_finish=date(2026, 9, 20),
                percent_complete=0,
                remaining_duration_days=12,
                status=ActivityStatus.not_started,
            ),
            Activity(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                project_id=project.id,
                project_scope_id=structural_scope.id,
                external_id="STR-1042",
                name="Zone C Slab Pour",
                discipline="Structural",
                planned_start=date(2026, 6, 1),
                planned_finish=date(2026, 7, 15),
                actual_start=date(2026, 6, 1),
                actual_finish=date(2026, 7, 18),
                percent_complete=100,
                remaining_duration_days=0,
                status=ActivityStatus.complete,
            ),
            Activity(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                project_id=project.id,
                project_scope_id=steel_scope.id,
                external_id="STL-1450",
                name="Roof Truss Erection – Bay 4",
                discipline="Structural Steel",
                planned_start=date(2026, 8, 1),
                planned_finish=date(2026, 9, 10),
                percent_complete=0,
                remaining_duration_days=28,
                status=ActivityStatus.not_started,
            ),
        ]
        db.add_all(activities)
        db.flush()

        by_ext_id = {a.external_id: a for a in activities}
        relationship = ActivityRelationship(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            predecessor_id=by_ext_id["MEP-2201"].id,
            successor_id=by_ext_id["MEP-2205"].id,
            link_type=LinkType.FS,
            lag_days=0,
        )
        db.add(relationship)
        db.flush()

        change_request = ChangeRequest(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            update_period_id=period.id,
            activity_relationship_id=relationship.id,
            requested_by_user_id=sub_user.id,
            field_changed="Predecessor lag",
            before_value="FS, 0d",
            after_value="FS, 5d",
            justification="Rough-in inspection pushed the tie-in date; need a 5-day lag to avoid trade stacking.",
            risk_level=RiskLevel.medium,
            status=ChangeRequestStatus.pending,
        )
        db.add(change_request)

        db.commit()
        print("Seeded tenant", TENANT_SLUG, "/ project", PROJECT_CODE)
        print("Company admin login:    admin@pokoena.com / ChangeMe123!")
        print("Company employee login: employee@pokoena.com / ChangeMe123!")
        print("Subcontractor login:    mep@pokoena.com / ChangeMe123!")
        print("(Create a platform admin separately with scripts.create_admin)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
