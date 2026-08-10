"""Seeds a demo project so the three Phase 1 screens have real data to render.

Usage (from backend/): python -m scripts.seed_demo

Idempotent: re-running skips creation if the project code already exists.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.change_request import ChangeRequest, ChangeRequestStatus, RiskLevel
from app.models.company import Company
from app.models.project import Project
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User, UserRole

PROJECT_CODE = "RLP-P2"


def main() -> None:
    db = SessionLocal()
    try:
        if db.query(Project).filter(Project.code == PROJECT_CODE).first():
            print(f"Project {PROJECT_CODE} already seeded — skipping.")
            return

        project = Project(id=uuid.uuid4(), name="Riverside Logistics Park — Phase 2", code=PROJECT_CODE)
        db.add(project)

        structural = Company(id=uuid.uuid4(), name="Structural Concrete Co.", discipline="Structural")
        mep = Company(id=uuid.uuid4(), name="MEP Systems Inc.", discipline="Mechanical/Electrical/Plumbing")
        steel = Company(id=uuid.uuid4(), name="Steel Erectors LLC", discipline="Structural Steel")
        db.add_all([structural, mep, steel])

        admin = User(
            id=uuid.uuid4(),
            email="admin@pokoena.com",
            hashed_password=hash_password("ChangeMe123!"),
            full_name="Jordan Diaz",
            role=UserRole.admin,
            is_active=True,
        )
        sub_user = User(
            id=uuid.uuid4(),
            email="mep@pokoena.com",
            hashed_password=hash_password("ChangeMe123!"),
            full_name="Riley Kim",
            role=UserRole.subcontractor,
            company_id=mep.id,
            is_active=True,
        )
        db.add_all([admin, sub_user])

        # Flush the parent rows (project/companies/users) before anything that
        # references them by foreign key: none of these models declare an ORM
        # relationship() to each other (kept deliberately plain-column, see the
        # models), so the unit-of-work has no dependency graph to auto-order
        # inserts by — without this, activities can get flushed before their
        # own project row exists and the FK constraint rejects them.
        db.flush()

        period = UpdatePeriod(
            id=uuid.uuid4(),
            project_id=project.id,
            period_number=14,
            label="Period 14",
            opens_at=datetime.now(timezone.utc) - timedelta(days=13),
            deadline_at=datetime.now(timezone.utc) + timedelta(days=3),
            status=UpdatePeriodStatus.open,
        )
        db.add(period)

        activities = [
            Activity(
                id=uuid.uuid4(),
                project_id=project.id,
                company_id=mep.id,
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
                project_id=project.id,
                company_id=mep.id,
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
                project_id=project.id,
                company_id=mep.id,
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
                project_id=project.id,
                company_id=mep.id,
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
                project_id=project.id,
                company_id=structural.id,
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
                project_id=project.id,
                company_id=steel.id,
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
        print("Seeded project", PROJECT_CODE)
        print("Admin login:        admin@pokoena.com / ChangeMe123!")
        print("Subcontractor login: mep@pokoena.com / ChangeMe123!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
