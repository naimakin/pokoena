from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(client, db_session, slug):
    tenant = create_tenant(db_session, name="Acme", slug=slug)
    project = create_project(db_session, tenant)
    admin = create_user(db_session, f"{slug}@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": f"{slug}@example.com", "password": "secret123"})
    with open(FIXTURE, "rb") as f:
        response = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert response.status_code == 201
    return project


def test_progress_summary_reports_both_versions_at_the_data_date(client, db_session):
    project = _setup(client, db_session, "progress-summary-1")

    response = client.get(f"/projects/{project.id}/evm/progress-summary")

    assert response.status_code == 200
    body = response.json()
    assert [v["kind"] for v in body["versions"]] == ["baseline", "latest"]
    assert body["planned_pct"] is not None and 0 <= body["planned_pct"] <= 100
    assert body["actual_pct"] is not None and 0 <= body["actual_pct"] <= 100
    latest = body["versions"][1]
    assert latest["tasks_total"] + latest["milestones_total"] > 0
    assert latest["tasks_remaining"] <= latest["tasks_total"]


def test_evm_summary_is_measured_at_the_data_date(client, db_session):
    project = _setup(client, db_session, "progress-summary-2")

    summary = client.get(f"/projects/{project.id}/evm/summary").json()
    progress = client.get(f"/projects/{project.id}/evm/progress-summary").json()

    assert summary["as_of_date"] == progress["data_date"]


def test_progress_curve_has_planned_throughout_and_actual_at_the_data_date(client, db_session):
    project = _setup(client, db_session, "progress-summary-3")

    body = client.get(f"/projects/{project.id}/evm/progress-curve").json()

    points = body["points"]
    assert len(points) >= 2
    assert all(p["planned"] is not None for p in points)
    assert points[-1]["planned"] == 100.0
    at_dd = next(p for p in points if p["date"] == body["data_date"])
    assert at_dd["actual"] is not None and at_dd["forecast"] is not None
    assert all(p["forecast"] is None for p in points if p["date"] < body["data_date"])


def test_dashboard_summary_falls_back_to_the_current_update(client, db_session):
    project = _setup(client, db_session, "progress-summary-4")

    body = client.get(f"/dashboard/summary?project_id={project.id}").json()

    assert body["active_period_id"] is None
    update = body["current_update"]
    assert update is not None
    assert update["activities_total"] > 0
    assert update["filename"] == "synthetic_project.xer"
    assert body["recovery_required"] == 0
