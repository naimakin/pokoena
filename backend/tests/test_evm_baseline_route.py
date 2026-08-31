from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-evm-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "evm-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _login(client):
    client.post("/auth/login", json={"email": "evm-admin@example.com", "password": "secret123"})


def _import_fixture(client, project_id):
    with open(FIXTURE, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )


def _activity_id(client, project_id, external_id: str) -> str:
    activities = client.get(f"/activities?project_id={project_id}").json()
    return next(a["id"] for a in activities if a["external_id"] == external_id)


def _active_baseline_id(client, project_id) -> str:
    return client.get(f"/projects/{project_id}/evm/baseline").json()["active_baseline"]["id"]


def test_quick_evm_with_no_resources_returns_zero_bac(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201

    response = client.get(f"/projects/{project.id}/evm/quick")

    assert response.status_code == 200
    body = response.json()
    assert body["bac"] == 0.0  # synthetic fixture has no RSRC/TASKRSRC data


def test_baseline_auto_locked_after_first_import(client, db_session):
    # A project's very first .xer upload auto-locks it as the baseline (see
    # services/baseline.py) — this fixture has duration-loaded activities and
    # planned dates, so it's immediately lockable.
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201

    response = client.get(f"/projects/{project.id}/evm/baseline")

    assert response.status_code == 200
    body = response.json()
    assert body["has_active"] is True
    active = body["active_baseline"]
    assert active["version_label"] == "Baseline"
    # A100(8) + A200(40) + A300(24) + A400(8) + A500(16) = 96 — A600 is a
    # zero-duration milestone, excluded from BAC same as the reference.
    assert active["total_budget_manhours"] == 96.0
    assert active["activity_count"] == 5
    assert active["target_start_date"] == "2026-01-05"
    assert active["target_end_date"] == "2026-01-14"


def test_manual_lock_conflicts_with_the_auto_locked_baseline(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201

    response = client.post(f"/projects/{project.id}/evm/baseline", json={"version_label": "Target-2"})

    assert response.status_code == 409


def test_manual_lock_after_superseding_the_auto_baseline_computes_bac(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201
    auto_baseline_id = _active_baseline_id(client, project.id)
    assert client.delete(f"/projects/{project.id}/evm/baseline/{auto_baseline_id}").status_code == 200

    response = client.post(f"/projects/{project.id}/evm/baseline", json={"version_label": "Target-1"})

    assert response.status_code == 201
    body = response.json()
    assert body["bac"] == 96.0
    assert body["activity_count"] == 5
    assert body["target_start"] == "2026-01-05"
    assert body["target_end"] == "2026-01-14"


def test_lock_baseline_rejects_reused_version_label_even_after_supersede(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201
    auto_baseline_id = _active_baseline_id(client, project.id)
    assert client.delete(f"/projects/{project.id}/evm/baseline/{auto_baseline_id}").status_code == 200

    first = client.post(f"/projects/{project.id}/evm/baseline", json={"version_label": "Target-1"})
    assert first.status_code == 201
    baseline_id = first.json()["baseline_id"]
    assert client.delete(f"/projects/{project.id}/evm/baseline/{baseline_id}").status_code == 200

    response = client.post(f"/projects/{project.id}/evm/baseline", json={"version_label": "Target-1"})
    assert response.status_code == 409

    assert client.post(f"/projects/{project.id}/evm/baseline", json={"version_label": "Target-2"}).status_code == 201


def test_scurve_requires_active_baseline(client, db_session):
    # No import at all — and therefore no auto-locked baseline — so the
    # guard in _require_active_baseline must still fire on its own.
    tenant, project = _setup(db_session)
    _login(client)

    response = client.get(f"/projects/{project.id}/evm/scurve")

    assert response.status_code == 423


def test_summary_zero_state_immediately_after_first_import(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201  # auto-locks the baseline

    response = client.get(f"/projects/{project.id}/evm/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "baseline_initialized"
    assert body["spi"] == 1.0
    assert body["cpi"] == 1.0


def test_submit_progress_updates_scurve_and_summary(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201  # auto-locks the baseline

    a100_id = _activity_id(client, project.id, "A100")

    response = client.post(
        f"/projects/{project.id}/evm/progress",
        json={"entries": [{"activity_id": a100_id, "entry_date": "2026-01-05", "burned_manhours_daily": 8.0}]},
    )
    assert response.status_code == 200
    assert response.json()["written"] == 1

    scurve = client.get(f"/projects/{project.id}/evm/scurve?granularity=daily").json()
    assert scurve["points"] > 0
    ac_values = [p["ac"] for p in scurve["series"]]
    assert max(ac_values) >= 8.0

    summary = client.get(f"/projects/{project.id}/evm/summary").json()
    assert summary["status"] == "active"
    assert summary["total_ac_raw"] == 8.0


def test_submit_progress_rejects_activity_outside_project(client, db_session):
    tenant, project = _setup(db_session)
    # Same tenant, different project — RLS wouldn't catch this (both rows are
    # tenant-visible), so it's the route's own project_id equality check that
    # must reject it.
    other_project = create_project(db_session, tenant, name="Other Project")
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201  # auto-locks the baseline
    assert _import_fixture(client, other_project.id).status_code == 201

    foreign_activity_id = _activity_id(client, other_project.id, "A100")

    response = client.post(
        f"/projects/{project.id}/evm/progress",
        json={"entries": [{"activity_id": foreign_activity_id, "entry_date": "2026-01-05", "burned_manhours_daily": 8.0}]},
    )

    assert response.status_code == 400


def test_supersede_baseline(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201  # auto-locks the baseline
    baseline_id = _active_baseline_id(client, project.id)

    response = client.delete(f"/projects/{project.id}/evm/baseline/{baseline_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "superseded"

    status_response = client.get(f"/projects/{project.id}/evm/baseline")
    assert status_response.json()["has_active"] is False


def test_supersede_already_superseded_baseline_conflicts(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import_fixture(client, project.id).status_code == 201  # auto-locks the baseline
    baseline_id = _active_baseline_id(client, project.id)
    client.delete(f"/projects/{project.id}/evm/baseline/{baseline_id}")

    response = client.delete(f"/projects/{project.id}/evm/baseline/{baseline_id}")

    assert response.status_code == 409
