from app.models.risk_item import RiskActionItem
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-risks")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "risk-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, admin


def _login(client, email="risk-admin@example.com"):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def test_create_lists_and_numbers(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    a = client.post(f"/projects/{project.id}/risks", json={"title": "Rain", "probability": 4, "impact": 5})
    b = client.post(f"/projects/{project.id}/risks", json={"title": "Permit", "probability": 2, "impact": 2})
    assert a.status_code == 201 and a.json()["code"] == "R-1" and a.json()["score"] == 20
    assert b.json()["code"] == "R-2"
    rows = client.get(f"/projects/{project.id}/risks").json()
    assert [r["code"] for r in rows] == ["R-1", "R-2"]  # score desc


def test_score_recomputed_on_edit(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    rid = client.post(f"/projects/{project.id}/risks", json={"title": "X", "probability": 2, "impact": 2}).json()["id"]
    out = client.patch(f"/projects/{project.id}/risks/{rid}", json={"probability": 5}).json()
    assert out["score"] == 10


def test_company_employee_without_edit_role_forbidden(client, db_session):
    tenant, project, _ = _setup(db_session)
    emp = create_user(db_session, "risk-emp@example.com", "secret123")
    add_membership(db_session, emp, tenant, TenantRole.company_employee, project_roles=[])
    _login(client, "risk-emp@example.com")
    r = client.post(f"/projects/{project.id}/risks", json={"title": "X"})
    assert r.status_code in (403, 404)


def test_cross_tenant_risk_not_found(client, db_session):
    tenant, project, admin = _setup(db_session)
    _login(client)
    rid = client.post(f"/projects/{project.id}/risks", json={"title": "X"}).json()["id"]

    other = create_tenant(db_session, name="Other", slug="other-risks")
    other_project = create_project(db_session, other)
    other_admin = create_user(db_session, "other-risk@example.com", "secret123")
    add_membership(db_session, other_admin, other, TenantRole.company_admin)
    _login(client, "other-risk@example.com")
    assert client.get(f"/projects/{other_project.id}/risks/{rid}").status_code in (403, 404)


def test_mitigation_submit_and_review(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    rid = client.post(f"/projects/{project.id}/risks", json={"title": "X", "probability": 4, "impact": 4}).json()["id"]

    # can't submit without a strategy
    assert client.post(f"/projects/{project.id}/risks/{rid}/mitigation/submit").status_code == 400
    client.patch(f"/projects/{project.id}/risks/{rid}", json={"mitigation_strategy": "mitigate"})
    # can't submit without items
    assert client.post(f"/projects/{project.id}/risks/{rid}/mitigation/submit").status_code == 400

    client.post(f"/projects/{project.id}/risks/{rid}/items", json={"action": "Expedite PO"})
    sub = client.post(f"/projects/{project.id}/risks/{rid}/mitigation/submit")
    assert sub.status_code == 200 and sub.json()["mitigation_status"] == "submitted"
    assert sub.json()["status"] == "mitigating"

    rev = client.post(
        f"/projects/{project.id}/risks/{rid}/mitigation/review",
        json={"decision": "needs_revision", "note": "more detail"},
    )
    assert rev.status_code == 200 and rev.json()["mitigation_status"] == "needs_revision"
    assert rev.json()["revision_no"] == 2
    # already-reviewed → 409 on a second review
    assert client.post(
        f"/projects/{project.id}/risks/{rid}/mitigation/review", json={"decision": "accept"}
    ).status_code == 409


def test_delete_cascades_items(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    rid = client.post(f"/projects/{project.id}/risks", json={"title": "X"}).json()["id"]
    client.post(f"/projects/{project.id}/risks/{rid}/items", json={"action": "one"})
    assert client.delete(f"/projects/{project.id}/risks/{rid}").status_code == 204
    assert db_session.query(RiskActionItem).count() == 0


def test_item_reorder(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    rid = client.post(f"/projects/{project.id}/risks", json={"title": "X"}).json()["id"]
    a = client.post(f"/projects/{project.id}/risks/{rid}/items", json={"action": "one"}).json()
    b = client.post(f"/projects/{project.id}/risks/{rid}/items", json={"action": "two"}).json()
    out = client.put(
        f"/projects/{project.id}/risks/{rid}/items/order", json={"ordered_item_ids": [b["id"], a["id"]]}
    ).json()
    assert [i["action"] for i in out] == ["two", "one"]


def test_embed_items(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    rid = client.post(f"/projects/{project.id}/risks", json={"title": "X"}).json()["id"]
    client.post(f"/projects/{project.id}/risks/{rid}/items", json={"action": "one"})
    rows = client.get(f"/projects/{project.id}/risks?embed_items=1").json()
    assert rows[0]["items"][0]["action"] == "one"
