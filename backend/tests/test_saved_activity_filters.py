from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-filters")
    project = create_project(db_session, tenant)
    a = create_user(db_session, "filt-a@example.com", "secret123")
    b = create_user(db_session, "filt-b@example.com", "secret123")
    add_membership(db_session, a, tenant, TenantRole.company_admin)
    add_membership(db_session, b, tenant, TenantRole.company_employee)
    return tenant, project


def _login(client, email):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def test_crud_round_trip(client, db_session):
    _, project = _setup(db_session)
    _login(client, "filt-a@example.com")
    crit = {"status": ["in_progress"], "predicates": [{"field": "external_id", "op": "contains", "value": "MEP"}]}

    created = client.post(
        f"/projects/{project.id}/saved-filters",
        json={"name": "Open MEP", "criteria": crit},
    )
    assert created.status_code == 201
    fid = created.json()["id"]
    assert created.json()["criteria"] == crit
    assert created.json()["is_owner"] is True

    listed = client.get(f"/projects/{project.id}/saved-filters").json()
    assert [f["name"] for f in listed] == ["Open MEP"]

    updated = client.put(
        f"/projects/{project.id}/saved-filters/{fid}",
        json={"name": "Open MEP work"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Open MEP work"

    assert client.delete(f"/projects/{project.id}/saved-filters/{fid}").status_code == 204
    assert client.get(f"/projects/{project.id}/saved-filters").json() == []


def test_duplicate_name_conflicts(client, db_session):
    _, project = _setup(db_session)
    _login(client, "filt-a@example.com")
    client.post(f"/projects/{project.id}/saved-filters", json={"name": "Dupe", "criteria": {}})
    again = client.post(f"/projects/{project.id}/saved-filters", json={"name": "Dupe", "criteria": {}})
    assert again.status_code == 409


def test_private_filter_isolated_between_users(client, db_session):
    _, project = _setup(db_session)
    _login(client, "filt-a@example.com")
    private_id = client.post(
        f"/projects/{project.id}/saved-filters", json={"name": "A private", "criteria": {}}
    ).json()["id"]
    shared_id = client.post(
        f"/projects/{project.id}/saved-filters",
        json={"name": "A shared", "criteria": {}, "is_shared": True},
    ).json()["id"]

    _login(client, "filt-b@example.com")
    names = {f["name"] for f in client.get(f"/projects/{project.id}/saved-filters").json()}
    assert names == {"A shared"}
    assert client.put(
        f"/projects/{project.id}/saved-filters/{shared_id}", json={"name": "hijack"}
    ).status_code == 403
    assert client.delete(f"/projects/{project.id}/saved-filters/{private_id}").status_code in (403, 404)


def test_filter_scoped_to_project(client, db_session):
    tenant, project = _setup(db_session)
    other = create_project(db_session, tenant, name="Other")
    _login(client, "filt-a@example.com")
    client.post(f"/projects/{project.id}/saved-filters", json={"name": "P1 only", "criteria": {}})
    assert client.get(f"/projects/{other.id}/saved-filters").json() == []


def test_oversized_criteria_rejected(client, db_session):
    _, project = _setup(db_session)
    _login(client, "filt-a@example.com")
    r = client.post(
        f"/projects/{project.id}/saved-filters",
        json={"name": "huge", "criteria": {"blob": "x" * 5000}},
    )
    assert r.status_code == 422


def test_subcontractor_forbidden(client, db_session):
    tenant, project = _setup(db_session)
    sub = create_user(db_session, "filt-sub@example.com", "secret123")
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    _login(client, "filt-sub@example.com")
    assert client.get(f"/projects/{project.id}/saved-filters").status_code == 403
