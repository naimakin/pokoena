from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "resource_loaded_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-bsl-prog")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "bsl-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _login(client, email="bsl-admin@example.com"):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def _upload(client, project_id, content: bytes, name="baseline.xer"):
    return client.post(
        f"/projects/{project_id}/evm/baseline/program",
        files={"file": (name, content, "application/octet-stream")},
    )


def test_first_upload_creates_the_baseline(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)

    response = _upload(client, project.id, FIXTURE.read_bytes())

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "created"
    assert body["baseline"]["version_label"] == "Baseline"
    assert body["baseline"]["total_budget_manhours"] == 96.0
    assert body["baseline"]["source_filename"] == "baseline.xer"
    assert client.get(f"/projects/{project.id}/evm/baseline").json()["has_active"] is True


def test_second_upload_overwrites_in_place(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)
    first = _upload(client, project.id, FIXTURE.read_bytes(), name="bsl_v1.xer")
    baseline_id = first.json()["baseline"]["id"]
    assert first.json()["baseline"]["target_start_date"] == "2026-01-05"

    shifted = FIXTURE.read_bytes().replace(b"2026-01-05 08:00", b"2026-02-05 08:00")
    second = _upload(client, project.id, shifted, name="bsl_v2.xer")

    assert second.status_code == 201
    body = second.json()
    assert body["mode"] == "overwritten"
    assert body["baseline"]["id"] == baseline_id  # same row, overwritten in place
    assert body["baseline"]["target_start_date"] == "2026-02-05"
    assert body["baseline"]["source_filename"] == "bsl_v2.xer"

    # Still exactly one baseline for the project.
    all_baselines = client.get(f"/projects/{project.id}/evm/baseline").json()["all_baselines"]
    assert len(all_baselines) == 1


def test_overwrite_refreshes_evm_snapshots_after_progress(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes())

    activities = client.get(f"/activities?project_id={project.id}").json()
    a100 = next(a["id"] for a in activities if a["external_id"] == "A100")
    client.post(
        f"/projects/{project.id}/evm/progress",
        json={"entries": [{"activity_id": a100, "entry_date": "2026-01-05", "burned_manhours_daily": 8.0}]},
    )

    shifted = FIXTURE.read_bytes().replace(b"2026-01-05 08:00", b"2026-02-05 08:00")
    assert _upload(client, project.id, shifted).status_code == 201

    summary = client.get(f"/projects/{project.id}/evm/summary").json()
    assert summary["status"] in ("active", "baseline_initialized")


def test_baseline_variance_reports_the_slip(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes())

    # A later update programme goes through Program Library, not the baseline
    # endpoint — it moves the live schedule but leaves the frozen baseline
    # alone, which is what makes a variance appear.
    shifted = FIXTURE.read_bytes().replace(b"2026-01-05 08:00", b"2026-02-05 08:00")
    resp = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("update_1.xer", shifted, "application/octet-stream")},
    )
    assert resp.status_code == 201

    variance = client.get(f"/projects/{project.id}/evm/baseline/variance").json()
    assert variance["summary"]["behind"] >= 1
    assert variance["summary"]["project_finish_variance_days"] > 0
    assert all(r["finish_variance_days"] >= 0 for r in variance["rows"])


def test_non_admin_cannot_upload_baseline_program(client, db_session):
    tenant, project = _setup(db_session)
    employee = create_user(db_session, "bsl-emp@example.com", "secret123")
    add_membership(db_session, employee, tenant, TenantRole.company_employee)
    _login(client, email="bsl-emp@example.com")

    response = _upload(client, project.id, FIXTURE.read_bytes())

    assert response.status_code == 403


def test_older_baseline_reupload_is_no_longer_blocked(client, db_session):
    # A baseline re-upload no longer touches the live schedule at all (see
    # baseline_non_destructive in services/xer_import.py), so an older data
    # date on the baseline file — the normal case, a baseline is supposed to
    # predate "now" — is expected and must not be blocked.
    _tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), name="bsl_v2.xer")  # data date 2026-01-05

    older = FIXTURE.read_bytes().replace(b"2026-01-05 08:00", b"2025-06-01 08:00")
    reuploaded = _upload(client, project.id, older, name="bsl_v1_again.xer")
    assert reuploaded.status_code == 201
    assert reuploaded.json()["mode"] == "overwritten"


def test_baseline_reupload_never_touches_live_current_schedule(client, db_session):
    # The bug this guards against: Planning -> Baselines uploads used to
    # overwrite the project's live activities/relationships and silently
    # re-point "Current update" at the baseline, even when a separate, newer
    # current update already existed — the root cause behind Dashboard/WBS/
    # Gantt/etc. showing baseline data instead of current data.
    _tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), name="bsl_v1.xer")  # data date 2026-01-05, first import

    # A real "current update" through Program Library, later than the baseline.
    shifted = FIXTURE.read_bytes().replace(b"2026-01-05 08:00", b"2026-03-01 08:00")
    resp = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("update_1.xer", shifted, "application/octet-stream")},
    )
    assert resp.status_code == 201
    current_import_id = resp.json()["id"]
    assert resp.json()["is_current"] is True

    activities_before = client.get(f"/activities?project_id={project.id}").json()
    assert len(activities_before) > 0

    # Re-uploading the (older) baseline file must not move "Current update"
    # back onto itself, and must not overwrite the live activities.
    reuploaded = _upload(client, project.id, FIXTURE.read_bytes(), name="bsl_v1_again.xer")
    assert reuploaded.status_code == 201
    assert reuploaded.json()["mode"] == "overwritten"

    imports = client.get(f"/projects/{project.id}/schedule-imports").json()
    current = next(i for i in imports if i["is_current"])
    assert current["id"] == current_import_id

    activities_after = client.get(f"/activities?project_id={project.id}").json()
    assert activities_after == activities_before


def test_rejects_non_xer(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)

    response = _upload(client, project.id, b"not a schedule", name="notes.txt")

    assert response.status_code == 400
