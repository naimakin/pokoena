import uuid
from datetime import date

from app.models.activity import Activity, ActivityStatus
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-deriv")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "deriv-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _activity(db_session, tenant, project, **kw) -> Activity:
    row = Activity(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        external_id=kw.pop("external_id", "A100"),
        name=kw.pop("name", "Mobilise"),
        discipline="General",
        status=kw.pop("status", ActivityStatus.not_started),
        percent_complete=kw.pop("percent_complete", 0),
        remaining_duration_days=kw.pop("remaining_duration_days", 5),
        target_duration_hours=kw.pop("target_duration_hours", 40.0),
        **kw,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _login(client):
    client.post("/auth/login", json={"email": "deriv-admin@example.com", "password": "secret123"})


def test_actual_start_only_marks_in_progress(client, db_session):
    tenant, project = _setup(db_session)
    a = _activity(db_session, tenant, project)
    _login(client)

    r = client.patch(f"/activities/{a.id}", json={"actual_start": "2026-02-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["actual_start"] == "2026-02-01"


def test_actual_finish_forces_complete_and_100(client, db_session):
    tenant, project = _setup(db_session)
    a = _activity(db_session, tenant, project, percent_complete=30)
    _login(client)

    r = client.patch(
        f"/activities/{a.id}",
        json={"actual_start": "2026-02-01", "actual_finish": "2026-02-10"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "complete"
    assert body["percent_complete"] == 100
    assert body["remaining_duration_days"] == 0


def test_actual_finish_without_start_is_rejected(client, db_session):
    tenant, project = _setup(db_session)
    a = _activity(db_session, tenant, project)
    _login(client)

    r = client.patch(f"/activities/{a.id}", json={"actual_finish": "2026-02-10"})
    assert r.status_code == 422


def test_actual_finish_before_start_is_rejected(client, db_session):
    tenant, project = _setup(db_session)
    a = _activity(db_session, tenant, project)
    _login(client)

    r = client.patch(
        f"/activities/{a.id}",
        json={"actual_start": "2026-02-10", "actual_finish": "2026-02-01"},
    )
    assert r.status_code == 422


def test_clearing_actuals_resets_to_not_started(client, db_session):
    tenant, project = _setup(db_session)
    a = _activity(
        db_session,
        tenant,
        project,
        status=ActivityStatus.complete,
        percent_complete=100,
        actual_start=date(2026, 2, 1),
        actual_finish=date(2026, 2, 10),
        remaining_duration_days=0,
    )
    _login(client)

    r = client.patch(f"/activities/{a.id}", json={"actual_start": None, "actual_finish": None})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_started"
    assert body["percent_complete"] == 0
    assert body["remaining_duration_days"] == 5  # 40h / 8


def test_percent_only_edit_keeps_legacy_three_way(client, db_session):
    tenant, project = _setup(db_session)
    a = _activity(db_session, tenant, project)
    _login(client)

    r = client.patch(f"/activities/{a.id}", json={"percent_complete": 55})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"
