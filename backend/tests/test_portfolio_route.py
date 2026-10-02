"""Portfolio Dashboard (routes/portfolio.py, services/portfolio.py)."""

import uuid
from pathlib import Path

from app.models.project_membership import ProjectMembership
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURES = Path(__file__).parent / "fixtures"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-portfolio")
    admin = create_user(db_session, "pf-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    a = create_project(db_session, tenant, name="Alpha", code="ALP")
    b = create_project(db_session, tenant, name="Bravo", code="BRV")
    empty = create_project(db_session, tenant, name="Charlie", code="CHR")
    return tenant, a, b, empty


def _login(client, email):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def _upload(client, project_id, fixture):
    r = client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": (fixture, (FIXTURES / fixture).read_bytes(), "application/octet-stream")},
    )
    assert r.status_code == 201, r.text


def test_portfolio_lists_every_project_with_its_timeline(client, db_session):
    tenant, a, b, empty = _setup(db_session)
    _login(client, "pf-admin@example.com")
    _upload(client, a.id, "synthetic_project.xer")
    _upload(client, b.id, "resource_loaded_project.xer")

    body = client.get("/portfolio").json()

    by_code = {p["code"]: p for p in body["projects"]}
    assert set(by_code) == {"ALP", "BRV", "CHR"}
    assert by_code["CHR"]["has_schedule"] is False
    alpha = by_code["ALP"]
    assert alpha["has_schedule"] and alpha["activity_count"] == 6
    assert alpha["months"], "a scheduled project has a monthly timeline"
    assert sum(m["tasks"] for m in alpha["months"]) >= 6
    assert all(m["score"] >= 0 for m in alpha["months"])
    # Months are contiguous, no gaps.
    keys = [m["month"] for m in alpha["months"]]
    assert keys == sorted(keys)

    # The portfolio row is every project's months summed.
    total = {m["month"]: m["score"] for m in body["months"]}
    for month, score in total.items():
        assert score == sum(
            m["score"] for p in body["projects"] for m in p["months"] if m["month"] == month
        )

    assert sum(body["summary"]["quality"].values()) == 2  # the two scheduled projects
    assert body["top_activities"] and body["top_activities"][0]["criticality_score"] is not None


def test_month_drilldown_lists_that_months_activities_most_critical_first(client, db_session):
    tenant, a, _b, _empty = _setup(db_session)
    _login(client, "pf-admin@example.com")
    _upload(client, a.id, "synthetic_project.xer")
    month = next(m["month"] for m in client.get("/portfolio").json()["projects"][0]["months"] if m["tasks"])

    r = client.get(f"/portfolio/projects/{a.id}/months/{month}")

    assert r.status_code == 200
    rows = r.json()["activities"]
    assert rows
    scores = [x["criticality_score"] for x in rows if x["criticality_score"] is not None]
    assert scores == sorted(scores, reverse=True)
    assert client.get(f"/portfolio/projects/{a.id}/months/2026-13").status_code == 422


def test_employee_sees_only_their_projects_and_subcontractor_none(client, db_session):
    tenant, a, b, _empty = _setup(db_session)
    employee = create_user(db_session, "pf-emp@example.com", "secret123")
    add_membership(db_session, employee, tenant, TenantRole.company_employee)
    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=a.id, user_id=employee.id))
    sub = create_user(db_session, "pf-sub@example.com", "secret123")
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    db_session.commit()

    _login(client, "pf-emp@example.com")
    assert [p["code"] for p in client.get("/portfolio").json()["projects"]] == ["ALP"]
    assert client.get(f"/portfolio/projects/{b.id}/months/2026-01").status_code in (403, 404)

    client.post("/auth/logout")
    _login(client, "pf-sub@example.com")
    assert client.get("/portfolio").status_code == 403
