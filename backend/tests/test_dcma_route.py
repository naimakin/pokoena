from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-dcma-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "dcma-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def test_dcma_report_requires_import_free_schedule_still_returns(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "dcma-admin@example.com", "password": "secret123"})

    response = client.get(f"/projects/{project.id}/dcma")

    assert response.status_code == 200
    body = response.json()
    assert body["total_activities"] == 0
    assert len(body["checks"]) == 14


def test_dcma_report_after_schedule_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "dcma-admin@example.com", "password": "secret123"})

    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert upload.status_code == 201

    response = client.get(f"/projects/{project.id}/dcma")
    assert response.status_code == 200
    body = response.json()

    assert body["total_activities"] == 6
    by_id = {c["id"]: c for c in body["checks"]}
    # The synthetic fixture has no RSRC/TASKRSRC data, so every non-milestone
    # in-scope activity is "unassigned" — check #10 is real now (Slice 6), not
    # not_tracked, since the route always loads (possibly empty) assignment
    # data. A600 (finish milestone) is excluded from the numerator (same
    # milestone exclusion as check #1) but still counts in the denominator:
    # 5 of 6 unassigned.
    assert by_id[10]["status"] == "warn"
    assert by_id[10]["pct"] == 83.33
    # A100 (Mobilization) has no predecessor and isn't a milestone, so it's a
    # genuine open end at the start of the network — A600 (finish milestone)
    # is excluded from the check by task type despite having no successor.
    assert by_id[1]["status"] == "fail"
    assert by_id[1]["details"] == ["A100"]
    # A400/A500 carry 40h of float — well under the 44-working-day (352h)
    # high-float threshold.
    assert by_id[6]["status"] == "pass"
    assert body["overall_score"] > 0
