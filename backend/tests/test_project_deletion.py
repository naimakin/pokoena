"""Portfolio > Projects: edit + hard delete. The delete test is the important
one — it populates one row in (almost) every table that carries `project_id`
or hangs off one transitively, deletes the project, and asserts every single
one of those rows is gone, and that a SECOND project/tenant's data survives
untouched. See services/project_deletion.py for why this has to be
enumerated by hand (no ON DELETE CASCADE on project_id anywhere)."""

import uuid
from datetime import date
from pathlib import Path

from app.models.activity import Activity
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.activity_event import ActivityEvent
from app.models.activity_relationship import ActivityRelationship
from app.models.baseline import (
    Baseline,
    BaselineActivity,
    BaselinePvCurve,
    BaselineResource,
    BaselineResourceAssignment,
    BaselineStatus,
)
from app.models.calendar import Calendar
from app.models.change_request import ChangeRequest, ChangeRequestStatus, RiskLevel
from app.models.dashboard_layout import DashboardLayout
from app.models.evm_snapshot import EvmSnapshot
from app.models.progress_entry import ProgressEntry
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import RecoveryPlan, RecoveryPlanItem
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.risk_item import RiskActionItem, RiskItem
from app.models.saved_activity_filter import SavedActivityFilter
from app.models.schedule_export import ScheduleExport
from app.models.schedule_import import ScheduleImport
from app.models.schedule_status_snapshot import ScheduleStatusSnapshot
from app.models.scope_submission import ScopeSubmission
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.update_period import UpdatePeriod
from app.models.user_tenant_role import TenantRole
from app.models.wbs_node import WbsNode
from tests.factories import add_membership, create_project, create_tenant, create_update_period, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-proj-delete-test")
    project = create_project(db_session, tenant, name="Doomed Project", code="DOOMED-1")
    admin = create_user(db_session, "delete-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, admin


def _login(client, email="delete-admin@example.com"):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def _populate_everything(client, db_session, tenant, project, admin):
    """Creates at least one row in every table that references this project,
    directly or transitively, using the real upload/baseline/progress
    pipeline where practical and direct inserts for the rest."""
    # --- schedule (real .xer import: activities, relationships, calendars,
    # resources, resource_assignments, schedule_imports, a status snapshot) ---
    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert upload.status_code == 201
    schedule_import_id = upload.json()["id"]
    a100 = db_session.query(Activity).filter(Activity.project_id == project.id, Activity.external_id == "A100").one()

    # --- baseline (+ children): the first import on a project auto-locks one
    # (see services/xer_import.py) — an EVM snapshot comes from a real progress entry ---
    baseline_status = client.get(f"/projects/{project.id}/evm/baseline").json()
    assert baseline_status["has_active"] is True
    progress_resp = client.post(
        f"/projects/{project.id}/evm/progress",
        json={"entries": [{"activity_id": str(a100.id), "entry_date": date.today().isoformat(), "burned_manhours_daily": 2}]},
    )
    assert progress_resp.status_code == 200

    # --- WBS node (manual, doesn't need an import) ---
    client.post(f"/projects/{project.id}/wbs-nodes", json={"wbs_short_name": "ROOT", "wbs_name": "Root"})

    # --- resource + assignment (the fixture carries no RSRC/TASKRSRC rows —
    # inserted directly), and their baseline-snapshot counterparts (normally
    # written by services/baseline.py at lock time, which already ran above
    # before these existed — inserted directly too, same reasoning) ---
    resource = Resource(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, rsrc_id="LAB1", name="Laborer")
    db_session.add(resource)
    db_session.flush()
    db_session.add(
        ResourceAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, activity_id=a100.id,
            resource_id=resource.id, target_qty=8.0,
        )
    )
    baseline = db_session.query(Baseline).filter(Baseline.project_id == project.id, Baseline.status == BaselineStatus.active).one()
    baseline_resource = BaselineResource(
        id=uuid.uuid4(), tenant_id=tenant.id, baseline_id=baseline.id, rsrc_id="LAB1", name="Laborer",
    )
    db_session.add(baseline_resource)
    db_session.flush()
    db_session.add(
        BaselineResourceAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, baseline_id=baseline.id, activity_id=a100.id,
            baseline_resource_id=baseline_resource.id, target_qty=8.0,
        )
    )

    # --- project membership ---
    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=admin.id))

    # --- risk item + action item (action item cascades via risk_item delete —
    # still asserted gone below, to prove the cascade actually fires) ---
    risk = RiskItem(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, code="R-1", title="Steel delay",
        probability=3, impact=3, score=9, created_by_user_id=admin.id,
    )
    db_session.add(risk)
    db_session.flush()
    db_session.add(
        RiskActionItem(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, risk_item_id=risk.id, action="Expedite")
    )

    # --- activity timeline (a comment + the change rows a PATCH writes) ---
    first_activity = db_session.query(Activity).filter(Activity.project_id == project.id).first()
    if first_activity is not None:
        client.post(f"/activities/{first_activity.id}/comments", json={"body": "Blocked on the permit"})
        client.patch(f"/activities/{first_activity.id}", json={"is_important": True})

    # --- recovery plan + item (item cascades via recovery_plan delete) ---
    plan = RecoveryPlan(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, activity_external_id="A100",
        activity_id=a100.id, created_by_user_id=admin.id,
    )
    db_session.add(plan)
    db_session.flush()
    db_session.add(
        RecoveryPlanItem(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, recovery_plan_id=plan.id, action="Add a shift")
    )

    # --- update period + change request + scope submission ---
    period = create_update_period(db_session, tenant, project)
    rel = db_session.query(ActivityRelationship).filter(ActivityRelationship.project_id == project.id).first()
    db_session.add(
        ChangeRequest(
            id=uuid.uuid4(), tenant_id=tenant.id, update_period_id=period.id,
            activity_relationship_id=rel.id if rel else None, activity_id=a100.id,
            requested_by_user_id=admin.id, field_changed="lag_days", before_value="0", after_value="2",
            justification="site condition", risk_level=RiskLevel.medium, status=ChangeRequestStatus.pending,
        )
    )
    sub_org = SubcontractorOrganization(id=uuid.uuid4(), tenant_id=tenant.id, name="MEP Co", discipline="MEP")
    db_session.add(sub_org)
    db_session.flush()
    db_session.add(
        ScopeSubmission(
            id=uuid.uuid4(), tenant_id=tenant.id, update_period_id=period.id,
            subcontractor_org_id=sub_org.id, submitted_by_user_id=admin.id,
        )
    )

    # --- project scope + subcontractor scope assignment ---
    scope = ProjectScope(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, name="MEP Scope", discipline="MEP")
    db_session.add(scope)
    db_session.flush()
    sub_user = create_user(db_session, "sub-delete-test@example.com", "secret123")
    add_membership(db_session, sub_user, tenant, TenantRole.subcontractor)
    db_session.add(
        SubcontractorScopeAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, user_id=sub_user.id, project_scope_id=scope.id, assigned_by_user_id=admin.id,
        )
    )

    # --- activity codes (type, value, task assignment) ---
    code_type = ActivityCodeType(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, actv_code_type_id="PHASE", name="Phase")
    db_session.add(code_type)
    db_session.flush()
    code_value = ActivityCodeValue(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, code_type_id=code_type.id,
        actv_code_id="P1", name="Phase 1",
    )
    db_session.add(code_value)
    db_session.flush()
    db_session.add(
        TaskActivityCode(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, activity_id=a100.id, code_value_id=code_value.id)
    )

    # --- dashboard layout + saved filter ---
    db_session.add(
        DashboardLayout(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=admin.id, widgets=[])
    )
    db_session.add(
        SavedActivityFilter(
            id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=admin.id,
            view_key="progress", name="My filter", criteria={},
        )
    )

    # --- schedule export ---
    db_session.add(
        ScheduleExport(
            id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, revision_no=1, revision_label="EXP-1",
            source_filename="export.xer", exported_by_user_id=admin.id,
        )
    )

    db_session.commit()
    return {"schedule_import_id": uuid.UUID(schedule_import_id), "a100_id": a100.id, "sub_org_id": sub_org.id}


_PROJECT_SCOPED_MODELS = [
    Activity, ActivityCodeType, ActivityCodeValue, TaskActivityCode, ActivityRelationship, ActivityEvent,
    Baseline, Calendar, DashboardLayout, EvmSnapshot, ProgressEntry, ProjectMembership, ProjectScope,
    RecoveryPlan, RecoveryPlanItem, Resource, ResourceAssignment, RiskItem, RiskActionItem,
    SavedActivityFilter, ScheduleExport, ScheduleImport, ScheduleStatusSnapshot, UpdatePeriod, WbsNode,
]

# These four only carry baseline_id (no project_id of their own — see
# models/baseline.py) — counted via a subquery on this project's baselines.
_BASELINE_CHILD_MODELS = [BaselineActivity, BaselinePvCurve, BaselineResource, BaselineResourceAssignment]


def _counts_for(db_session, project_id, baseline_ids: list):
    counts = {m.__tablename__: db_session.query(m).filter(m.project_id == project_id).count() for m in _PROJECT_SCOPED_MODELS}
    counts.update(
        {m.__tablename__: db_session.query(m).filter(m.baseline_id.in_(baseline_ids)).count() for m in _BASELINE_CHILD_MODELS}
    )
    return counts


def test_delete_project_wipes_every_related_table_but_leaves_others_untouched(client, db_session):
    tenant, project, admin = _setup(db_session)
    _login(client)
    ids = _populate_everything(client, db_session, tenant, project, admin)

    # A second, untouched project in the SAME tenant — the control group.
    other_project = create_project(db_session, tenant, name="Survivor", code="KEEP-1")
    other_activity = Activity(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=other_project.id, external_id="X1", name="X1",
        discipline="General", percent_complete=0, remaining_duration_days=1,
    )
    db_session.add(other_activity)
    db_session.commit()

    # Captured up front: the route's own commit (inside the DELETE call below)
    # expires every object in this shared test session, including `project`
    # itself — nothing below dereferences `project.id`/`.code` after that.
    project_id, project_code = project.id, project.code

    baseline_ids = [b.id for b in db_session.query(Baseline.id).filter(Baseline.project_id == project_id)]
    assert baseline_ids, "setup didn't lock a baseline"
    before = _counts_for(db_session, project_id, baseline_ids)
    assert all(v > 0 for v in before.values()), f"setup didn't populate everything: {before}"
    # Cross-project rows not directly keyed by project_id, but hanging off
    # this project's rows — spot-checked separately below since they aren't
    # in _PROJECT_SCOPED_MODELS.
    assert db_session.query(ChangeRequest).filter(ChangeRequest.update_period_id.in_(
        db_session.query(UpdatePeriod.id).filter(UpdatePeriod.project_id == project_id)
    )).count() == 1
    assert db_session.query(ScopeSubmission).filter(ScopeSubmission.update_period_id.in_(
        db_session.query(UpdatePeriod.id).filter(UpdatePeriod.project_id == project_id)
    )).count() == 1
    sub_scope_ids = db_session.query(ProjectScope.id).filter(ProjectScope.project_id == project_id)
    assert db_session.query(SubcontractorScopeAssignment).filter(
        SubcontractorScopeAssignment.project_scope_id.in_(sub_scope_ids)
    ).count() == 1

    response = client.delete(f"/projects/{project_id}?confirm_code={project_code}")

    assert response.status_code == 204
    after = _counts_for(db_session, project_id, baseline_ids)
    assert all(v == 0 for v in after.values()), f"leftover rows after delete: {after}"
    assert db_session.query(ChangeRequest).count() == 0
    assert db_session.query(ScopeSubmission).count() == 0
    assert db_session.query(SubcontractorScopeAssignment).count() == 0
    assert db_session.query(Project).filter(Project.id == project_id).first() is None

    # The other project (same tenant) and shared, non-project-scoped rows survive.
    assert db_session.query(Project).filter(Project.id == other_project.id).first() is not None
    assert db_session.query(Activity).filter(Activity.id == other_activity.id).first() is not None
    assert db_session.query(SubcontractorOrganization).filter(SubcontractorOrganization.id == ids["sub_org_id"]).first() is not None


def test_delete_project_requires_the_matching_confirm_code(client, db_session):
    tenant, project, admin = _setup(db_session)
    _login(client)

    response = client.delete(f"/projects/{project.id}?confirm_code=WRONG")

    assert response.status_code == 400
    assert db_session.query(Project).filter(Project.id == project.id).first() is not None


def test_delete_project_needs_company_admin(client, db_session):
    tenant, project, admin = _setup(db_session)
    employee = create_user(db_session, "employee-delete-test@example.com", "secret123")
    add_membership(db_session, employee, tenant, TenantRole.company_employee)
    client.post("/auth/login", json={"email": "employee-delete-test@example.com", "password": "secret123"})

    response = client.delete(f"/projects/{project.id}?confirm_code={project.code}")

    assert response.status_code == 403
    assert db_session.query(Project).filter(Project.id == project.id).first() is not None


def test_update_project_name_and_code(client, db_session):
    tenant, project, admin = _setup(db_session)
    _login(client)

    response = client.patch(f"/projects/{project.id}", json={"name": "Renamed", "code": "NEW-CODE"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["code"] == "NEW-CODE"


def test_update_project_rejects_a_duplicate_code(client, db_session):
    tenant, project, admin = _setup(db_session)
    create_project(db_session, tenant, name="Other", code="TAKEN")
    _login(client)

    response = client.patch(f"/projects/{project.id}", json={"code": "TAKEN"})

    assert response.status_code == 409


def test_update_project_rejects_empty_payload(client, db_session):
    tenant, project, admin = _setup(db_session)
    _login(client)

    assert client.patch(f"/projects/{project.id}", json={}).status_code == 422
