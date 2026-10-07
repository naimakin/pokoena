import uuid

from app.models.activity import Activity, ActivityStatus
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user


def _login(client, email="dash-admin@example.com", password="secret123"):
    client.post("/auth/login", json={"email": email, "password": password})


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug=f"acme-dash-{uuid.uuid4().hex[:6]}")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "dash-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def test_layout_defaults_when_never_configured(client, db_session):
    _, project = _setup(db_session)
    _login(client)

    res = client.get(f"/dashboard/layout?project_id={project.id}")

    assert res.status_code == 200
    body = res.json()
    assert body["is_default"] is True
    assert body["theme_key"] == "calm"
    keys = {w["key"] for w in body["widgets"]}
    assert "s-curve" in keys and "health-badge" in keys
    assert all(w["enabled"] for w in body["widgets"])


def test_layout_round_trips_and_persists(client, db_session):
    _, project = _setup(db_session)
    _login(client)

    payload = {
        "project_id": str(project.id),
        "theme_key": "mono-amber",
        "widgets": [
            {"key": "health-badge", "order": 0, "enabled": True, "options": {}},
            {"key": "s-curve", "order": 1, "enabled": False, "options": {}},
        ],
    }
    put = client.put("/dashboard/layout", json=payload)
    assert put.status_code == 200
    assert put.json()["is_default"] is False
    assert put.json()["theme_key"] == "mono-amber"

    got = client.get(f"/dashboard/layout?project_id={project.id}").json()
    assert got["is_default"] is False
    assert got["theme_key"] == "mono-amber"
    by_key = {w["key"]: w for w in got["widgets"]}
    assert by_key["s-curve"]["enabled"] is False
    # Catalogue widgets the user didn't save come back appended + disabled.
    assert by_key["scope-table"]["enabled"] is False


def test_layout_rejects_unknown_widget_key(client, db_session):
    _, project = _setup(db_session)
    _login(client)

    res = client.put(
        "/dashboard/layout",
        json={
            "project_id": str(project.id),
            "theme_key": "calm",
            "widgets": [{"key": "totally-made-up", "order": 0, "enabled": True, "options": {}}],
        },
    )
    assert res.status_code == 400


def test_layout_rejects_unknown_theme(client, db_session):
    _, project = _setup(db_session)
    _login(client)

    res = client.put(
        "/dashboard/layout",
        json={"project_id": str(project.id), "theme_key": "neon", "widgets": []},
    )
    assert res.status_code == 422


def test_layout_is_per_user(client, db_session):
    tenant, project = _setup(db_session)
    employee = create_user(db_session, "dash-emp@example.com", "secret123")
    add_membership(db_session, employee, tenant, TenantRole.company_admin)

    _login(client)
    client.put(
        "/dashboard/layout",
        json={
            "project_id": str(project.id),
            "theme_key": "high-contrast",
            "widgets": [{"key": "recovery", "order": 0, "enabled": True, "options": {}}],
        },
    )

    _login(client, email="dash-emp@example.com")
    got = client.get(f"/dashboard/layout?project_id={project.id}").json()
    assert got["is_default"] is True  # the other user's layout doesn't leak


def test_layout_cross_tenant_is_403(client, db_session):
    tenant_a = create_tenant(db_session, name="A", slug=f"a-{uuid.uuid4().hex[:6]}")
    tenant_b = create_tenant(db_session, name="B", slug=f"b-{uuid.uuid4().hex[:6]}")
    admin_a = create_user(db_session, "a-admin@example.com", "secret123")
    add_membership(db_session, admin_a, tenant_a, TenantRole.company_admin)
    project_b = create_project(db_session, tenant_b, name="B project")

    _login(client, email="a-admin@example.com")

    assert client.get(f"/dashboard/layout?project_id={project_b.id}").status_code == 403
    assert (
        client.put(
            "/dashboard/layout",
            json={"project_id": str(project_b.id), "theme_key": "calm", "widgets": []},
        ).status_code
        == 403
    )


def test_health_and_risk_degrade_gracefully_on_empty_project(client, db_session):
    _, project = _setup(db_session)
    _login(client)

    health = client.get(f"/dashboard/health?project_id={project.id}")
    assert health.status_code == 200
    assert health.json()["score"] is None
    assert health.json()["status"] == "unknown"

    risks = client.get(f"/dashboard/risk-highlights?project_id={project.id}")
    assert risks.status_code == 200
    assert risks.json() == []


def test_risk_highlights_flags_overdue_and_negative_float(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)

    db_session.add(
        Activity(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            external_id="A-100",
            name="Slab pour",
            discipline="Structure",
            planned_finish=None,
            percent_complete=20,
            remaining_duration_days=3,
            status=ActivityStatus.in_progress,
            total_float_hours=-40.0,
            is_critical=True,
        )
    )
    db_session.commit()

    risks = client.get(f"/dashboard/risk-highlights?project_id={project.id}").json()
    assert any("Negative float" in r["title"] for r in risks)
    assert risks[0]["severity"] == "high"

    health = client.get(f"/dashboard/health?project_id={project.id}").json()
    cp = next(f for f in health["factors"] if f["label"] == "Critical path")
    assert cp["status"] == "crit"
    # Every factor carries the stable key the dashboard uses to link to its detail page.
    assert cp["key"] == "critical_path"
    assert {f["key"] for f in health["factors"]} <= {
        "scope_submissions",
        "evm",
        "critical_path",
        "overdue",
    }


def test_risk_highlights_include_high_score_register_risks(client, db_session):
    tenant, project = _setup(db_session)
    admin = create_user(db_session, "dash-r2@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    from tests.factories import create_risk_item

    create_risk_item(db_session, tenant, project, admin, code="R-1", title="Crane availability", probability=5, impact=4)
    _login(client)

    risks = client.get(f"/dashboard/risk-highlights?project_id={project.id}").json()
    assert any(r["source"] == "Risk register" and "Crane availability" in r["title"] for r in risks)


def test_saved_flagged_widget_becomes_recovery(client, db_session):
    """Flag Reviews were removed; a layout saved with their widget shows the
    Recovery plans widget in that slot instead of losing it."""
    import uuid as _uuid

    from app.models.dashboard_layout import DashboardLayout

    tenant, project = _setup(db_session)
    admin = create_user(db_session, "dash-flagged@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    db_session.add(
        DashboardLayout(
            id=_uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=admin.id, theme_key="calm",
            widgets=[{"key": "flagged", "order": 0, "enabled": True, "options": {}}],
        )
    )
    db_session.commit()
    _login(client, email="dash-flagged@example.com")

    widgets = client.get(f"/dashboard/layout?project_id={project.id}").json()["widgets"]

    first = min(widgets, key=lambda w: w["order"])
    assert first["key"] == "recovery" and first["enabled"] is True
    assert "flagged" not in {w["key"] for w in widgets}
