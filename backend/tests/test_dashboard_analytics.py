from datetime import date
from pathlib import Path

import pytest

from app.models.user_tenant_role import TenantRole
from app.services.analytics import spread_by_month
from tests.factories import add_membership, create_project, create_tenant, create_user

RESOURCE_FIXTURE = Path(__file__).parent / "fixtures" / "resource_loaded_project.xer"


def test_spread_splits_by_calendar_days_per_month():
    out = spread_by_month(62.0, date(2025, 1, 1), date(2025, 2, 28))  # 31 + 28 days
    assert out["2025-01"] == pytest.approx(62.0 * 31 / 59)
    assert out["2025-02"] == pytest.approx(62.0 * 28 / 59)
    assert sum(out.values()) == pytest.approx(62.0)


def test_spread_collapses_a_missing_end_and_skips_zero():
    assert spread_by_month(10.0, date(2025, 3, 4), None) == {"2025-03": 10.0}
    assert spread_by_month(0.0, date(2025, 3, 4), date(2025, 4, 4)) == {}
    assert spread_by_month(10.0, None, None) == {}


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-analytics")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "analytics-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _login(client):
    client.post("/auth/login", json={"email": "analytics-admin@example.com", "password": "secret123"})


def test_analytics_needs_a_baseline(client, db_session):
    _, project = _setup(db_session)
    _login(client)
    assert client.get(f"/dashboard/analytics?project_id={project.id}").status_code == 423


def test_analytics_rolls_up_baseline_hours_and_cost(client, db_session):
    _, project = _setup(db_session)
    _login(client)
    res = client.post(
        f"/projects/{project.id}/evm/baseline/program",
        files={"file": (RESOURCE_FIXTURE.name, RESOURCE_FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert res.status_code == 201

    res = client.get(f"/dashboard/analytics?project_id={project.id}")
    assert res.status_code == 200
    body = res.json()

    # Same totals as the Baselines page: 96 labor hours, 14 600 in cost.
    assert body["hours"]["budget"] == 96.0
    assert body["cost"]["budget"] == 14600.0
    assert body["currency"] == "EUR"
    # Monthly planned spread adds back up to the budget.
    assert sum(m["planned_hours"] for m in body["months"]) == pytest.approx(96.0, abs=0.05)
    assert sum(m["planned_cost"] for m in body["months"]) == pytest.approx(14600.0, abs=0.5)
    assert body["planned_pct"] is None or 0 <= body["planned_pct"] <= 100
    for grouping in body["groupings"]:
        assert len(grouping["groups"]) >= 2
