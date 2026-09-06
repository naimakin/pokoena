import uuid

from app.models.activity import Activity, ActivityStatus
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user


def _activity(db_session, tenant, project, code, **kw) -> Activity:
    row = Activity(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        external_id=code,
        name=f"Activity {code}",
        discipline="General",
        status=ActivityStatus.not_started,
        percent_complete=0,
        remaining_duration_days=5,
        target_duration_hours=40.0,
        **kw,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-batch")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "batch-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _login(client, email="batch-admin@example.com"):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def test_batch_happy_path(client, db_session):
    tenant, project = _setup(db_session)
    a1 = _activity(db_session, tenant, project, "A100")
    a2 = _activity(db_session, tenant, project, "A200")
    _login(client)

    r = client.patch(
        f"/activities?project_id={project.id}",
        json={
            "updates": [
                {"id": str(a1.id), "actual_start": "2026-02-01"},
                {"id": str(a2.id), "actual_start": "2026-02-01", "actual_finish": "2026-02-05"},
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["saved"]) == 2
    assert body["failed"] == []
    by_id = {row["id"]: row for row in body["saved"]}
    assert by_id[str(a1.id)]["status"] == "in_progress"
    assert by_id[str(a2.id)]["status"] == "complete"
    assert by_id[str(a2.id)]["percent_complete"] == 100


def test_batch_one_bad_row_others_saved(client, db_session):
    tenant, project = _setup(db_session)
    a1 = _activity(db_session, tenant, project, "A100")
    a2 = _activity(db_session, tenant, project, "A200")
    _login(client)

    r = client.patch(
        f"/activities?project_id={project.id}",
        json={
            "updates": [
                {"id": str(a1.id), "actual_start": "2026-02-01"},
                {"id": str(a2.id), "actual_finish": "2026-02-05"},  # no actual_start → fails
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert [row["id"] for row in body["saved"]] == [str(a1.id)]
    assert [row["id"] for row in body["failed"]] == [str(a2.id)]

    db_session.expire_all()
    assert db_session.get(Activity, a1.id).status == ActivityStatus.in_progress
    assert db_session.get(Activity, a2.id).status == ActivityStatus.not_started
    assert db_session.get(Activity, a2.id).actual_finish is None


def test_batch_unknown_id_reported(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    ghost = uuid.uuid4()
    r = client.patch(
        f"/activities?project_id={project.id}",
        json={"updates": [{"id": str(ghost), "actual_start": "2026-02-01"}]},
    )
    assert r.status_code == 200
    assert r.json()["failed"][0]["id"] == str(ghost)


def test_batch_cross_tenant_activity_not_touched(client, db_session):
    tenant, project = _setup(db_session)
    other_tenant = create_tenant(db_session, name="Other", slug="other-batch")
    other_project = create_project(db_session, other_tenant)
    victim = _activity(db_session, other_tenant, other_project, "X900")
    _login(client)

    r = client.patch(
        f"/activities?project_id={project.id}",
        json={"updates": [{"id": str(victim.id), "actual_start": "2026-02-01"}]},
    )
    assert r.status_code == 200
    assert r.json()["saved"] == []
    db_session.expire_all()
    assert db_session.get(Activity, victim.id).actual_start is None


def test_batch_company_employee_without_edit_role_forbidden(client, db_session):
    tenant, project = _setup(db_session)
    a1 = _activity(db_session, tenant, project, "A100")
    emp = create_user(db_session, "emp@example.com", "secret123")
    add_membership(db_session, emp, tenant, TenantRole.company_employee, project_roles=[])
    _login(client, "emp@example.com")

    r = client.patch(
        f"/activities?project_id={project.id}",
        json={"updates": [{"id": str(a1.id), "actual_start": "2026-02-01"}]},
    )
    assert r.status_code in (403, 404)
