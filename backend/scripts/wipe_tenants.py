"""One-off CLI to hard-delete every tenant and everything scoped to it —
companies, projects, invites, activities, memberships, all of it — plus any
non-platform-admin user left behind once their tenant is gone. Platform admin
users (and their own tenant_id=NULL audit trail) are never touched.

Destructive and irreversible: this is for clearing out test/demo data during
early development, not something to run once real tenant data exists.

Usage (from backend/, with DATABASE_URL pointed at a role with full DML
rights on every table — e.g. run it the same way as create_admin.py/
seed_demo.py, feeding the `db_url` secret into DATABASE_URL_FILE so RLS is
bypassed for every tenant, not just whichever one happens to be current):
    python -m scripts.wipe_tenants --yes
"""

import argparse

from app.db.session import SessionLocal
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.audit_log import AuditLog
from app.models.change_request import ChangeRequest
from app.models.invite import Invite
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.scope_submission import ScopeSubmission
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.tenant import Tenant
from app.models.update_period import UpdatePeriod
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.user_tenant_role import UserTenantRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Hard-delete every tenant and all its data")
    parser.add_argument(
        "--yes", action="store_true", required=True, help="Required — confirms this is intentional"
    )
    parser.parse_args()

    db = SessionLocal()
    try:
        tenant_count = db.query(Tenant).count()

        # Children before parents, in the exact FK order laid out in
        # backend/alembic/versions/0001_initial_schema.py.
        db.query(AuditLog).filter(AuditLog.tenant_id.isnot(None)).delete(synchronize_session=False)
        db.query(ScopeSubmission).delete(synchronize_session=False)
        db.query(ChangeRequest).delete(synchronize_session=False)
        db.query(ActivityRelationship).delete(synchronize_session=False)
        db.query(Activity).delete(synchronize_session=False)
        db.query(UpdatePeriod).delete(synchronize_session=False)
        db.query(SubcontractorScopeAssignment).delete(synchronize_session=False)
        db.query(ProjectMembership).delete(synchronize_session=False)
        db.query(Invite).delete(synchronize_session=False)
        db.query(ProjectScope).delete(synchronize_session=False)
        db.query(Project).delete(synchronize_session=False)
        db.query(UserTenantRole).delete(synchronize_session=False)
        db.query(SubcontractorOrganization).delete(synchronize_session=False)
        db.query(Tenant).delete(synchronize_session=False)

        orphaned_user_ids = [
            row[0] for row in db.query(User.id).filter(User.is_platform_admin.is_(False)).all()
        ]
        db.query(UserIdentity).filter(UserIdentity.user_id.in_(orphaned_user_ids)).delete(
            synchronize_session=False
        )
        user_count = (
            db.query(User).filter(User.is_platform_admin.is_(False)).delete(synchronize_session=False)
        )

        db.commit()
        print(
            f"Wiped {tenant_count} tenant(s) and all their data. "
            f"Deleted {user_count} non-platform-admin user(s). Platform admins were left untouched."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
