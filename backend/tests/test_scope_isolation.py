import uuid
from datetime import datetime, timedelta, timezone

from app.models.activity import Activity, ActivityStatus
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_project_scope, create_tenant, create_user


def _activity(db_session, tenant, project, scope, external_id):
    activity = Activity(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        project_scope_id=scope.id,
        external_id=external_id,
        name=f"Activity {external_id}",
        discipline="General",
        percent_complete=0,
        remaining_duration_days=5,
        status=ActivityStatus.not_started,
    )
    db_session.add(activity)
    db_session.commit()
    return activity


def _setup_two_scopes(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-scope-test")
    project = create_project(db_session, tenant)
    scope_1 = create_project_scope(db_session, tenant, project, name="Scope 1", discipline="MEP")
    scope_2 = create_project_scope(db_session, tenant, project, name="Scope 2", discipline="Structural")

    sub_1 = create_user(db_session, "sub1@example.com", "secret123")
    admin = create_user(db_session, "scope-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    add_membership(db_session, sub_1, tenant, TenantRole.subcontractor)
    db_session.add(
        SubcontractorScopeAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id=sub_1.id,
            project_scope_id=scope_1.id,
            assigned_by_user_id=admin.id,
        )
    )
    db_session.add(
        UpdatePeriod(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            period_number=1,
            label="Period 1",
            opens_at=datetime.now(timezone.utc) - timedelta(days=1),
            deadline_at=datetime.now(timezone.utc) + timedelta(days=7),
            status=UpdatePeriodStatus.open,
        )
    )
    db_session.commit()

    activity_in_scope_1 = _activity(db_session, tenant, project, scope_1, "SCOPE1-001")
    activity_in_scope_2 = _activity(db_session, tenant, project, scope_2, "SCOPE2-001")
    return tenant, project, activity_in_scope_1, activity_in_scope_2


def test_subcontractor_cannot_patch_activity_outside_assigned_scope(client, db_session):
    _tenant, _project, _in_scope, out_of_scope = _setup_two_scopes(db_session)

    client.post("/auth/login", json={"email": "sub1@example.com", "password": "secret123"})

    response = client.patch(f"/activities/{out_of_scope.id}", json={"percent_complete": 50})

    assert response.status_code == 403


def test_subcontractor_can_patch_activity_inside_assigned_scope(client, db_session):
    _tenant, _project, in_scope, _out_of_scope = _setup_two_scopes(db_session)

    client.post("/auth/login", json={"email": "sub1@example.com", "password": "secret123"})

    response = client.patch(f"/activities/{in_scope.id}", json={"percent_complete": 50})

    assert response.status_code == 200
    assert response.json()["percent_complete"] == 50


def test_subcontractor_activity_list_only_shows_assigned_scope(client, db_session):
    tenant, project, in_scope, out_of_scope = _setup_two_scopes(db_session)

    client.post("/auth/login", json={"email": "sub1@example.com", "password": "secret123"})

    response = client.get(f"/activities?project_id={project.id}")

    assert response.status_code == 200
    external_ids = {a["external_id"] for a in response.json()}
    assert external_ids == {in_scope.external_id}
    assert out_of_scope.external_id not in external_ids


def test_subcontractor_cannot_view_relationships_outside_scope(client, db_session):
    _tenant, _project, _in_scope, out_of_scope = _setup_two_scopes(db_session)

    client.post("/auth/login", json={"email": "sub1@example.com", "password": "secret123"})

    response = client.get(f"/activities/{out_of_scope.id}/relationships")

    assert response.status_code == 403
