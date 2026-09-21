"""Program Library: which import is the Baseline / the Current update, editable
data date, and reversible unlock."""

from datetime import datetime, timedelta, timezone

from app.models.activity import Activity
from app.models.user import User
from tests.factories import create_schedule_import
from tests.test_schedule_import import COMPLETED_FIXTURE, _set_imported_at, _setup, _upload


def _admin(db_session):
    return db_session.query(User).filter(User.email == "xer-admin@example.com").one()


def _login(client):
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})


def _upload_completed(client, project_id):
    with open(COMPLETED_FIXTURE, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": ("completed_not_critical.xer", f.read(), "application/octet-stream")},
        )


def _imports(client, project_id):
    return {i["id"]: i for i in client.get(f"/projects/{project_id}/schedule-imports").json()}


def _two_imports(client, db_session, project_id):
    """A = synthetic (data date 2026-01-05, auto-locked baseline), then B = completed
    fixture (2026-01-12). B is the newest, so it's the current update."""
    base = datetime.now(timezone.utc)
    a = _upload(client, project_id).json()
    _set_imported_at(db_session, a["id"], base)
    b = _upload_completed(client, project_id).json()
    _set_imported_at(db_session, b["id"], base + timedelta(minutes=1))
    return a, b


def test_newest_upload_is_current_and_every_upload_keeps_its_file(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a, b = _two_imports(client, db_session, project.id)

    listed = _imports(client, project.id)
    assert listed[b["id"]]["is_current"] is True
    assert listed[a["id"]]["is_current"] is False
    assert listed[a["id"]]["has_source_file"] and listed[b["id"]]["has_source_file"]


def test_set_current_rebuilds_the_live_schedule_from_the_stored_file(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a, b = _two_imports(client, db_session, project.id)
    by_code = {x["external_id"]: x for x in client.get(f"/activities?project_id={project.id}").json()}
    # B (completed fixture) is live: C200 is the critical successor, A300 not overwritten yet.
    assert by_code["C200"]["is_critical"] is True

    response = client.post(f"/projects/{project.id}/schedule-imports/{a['id']}/set-current")

    assert response.status_code == 200
    assert response.json()["is_current"] is True
    listed = _imports(client, project.id)
    assert listed[a["id"]]["is_current"] is True and listed[b["id"]]["is_current"] is False
    db_session.expire_all()
    by_code = {x["external_id"]: x for x in client.get(f"/activities?project_id={project.id}").json()}
    assert by_code["A300"]["is_critical"] is True  # A's own CPM result is live again
    assert by_code["A300"]["total_float_hours"] == 0
    assert by_code["A500"]["total_float_hours"] == 40
    # No new import row, no relabel — A keeps the metadata it already had.
    assert len(listed) == 2
    assert listed[a["id"]]["revision_label"] == a["revision_label"]


def test_set_current_is_idempotent_for_the_current_import(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a, b = _two_imports(client, db_session, project.id)

    response = client.post(f"/projects/{project.id}/schedule-imports/{b['id']}/set-current")

    assert response.status_code == 200
    assert _imports(client, project.id)[b["id"]]["is_current"] is True


def test_set_current_needs_the_stored_file(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a, b = _two_imports(client, db_session, project.id)
    legacy = create_schedule_import(db_session, tenant, project, _admin(db_session), revision_no=9, revision_label="UPD-9")
    _set_imported_at(db_session, str(legacy.id), datetime.now(timezone.utc) - timedelta(days=30))

    response = client.post(f"/projects/{project.id}/schedule-imports/{legacy.id}/set-current")

    assert response.status_code == 409
    assert "Upload the .xer again" in response.json()["detail"]
    assert _imports(client, project.id)[b["id"]]["is_current"] is True


def test_the_current_import_cannot_be_deleted_even_when_it_is_not_the_newest(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a, b = _two_imports(client, db_session, project.id)
    # Unlock first: A is the auto-locked baseline, and a baseline import can't be deleted.
    active = client.get(f"/projects/{project.id}/evm/baseline").json()["active_baseline"]
    client.delete(f"/projects/{project.id}/evm/baseline/{active['id']}")
    client.post(f"/projects/{project.id}/schedule-imports/{a['id']}/set-current")

    blocked = client.delete(f"/projects/{project.id}/schedule-imports/{a['id']}")
    allowed = client.delete(f"/projects/{project.id}/schedule-imports/{b['id']}")

    assert blocked.status_code == 409 and "current schedule" in blocked.json()["detail"]
    assert allowed.status_code == 204


def test_edit_data_date_keeps_the_time_of_day_and_needs_something_to_change(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a = _upload(client, project.id).json()
    url = f"/projects/{project.id}/schedule-imports/{a['id']}"

    response = client.patch(url, json={"data_date": "2026-02-10", "revision_label": "Feb close"})

    assert response.status_code == 200
    body = response.json()
    assert body["data_date"].startswith("2026-02-10")
    assert body["data_date"][10:] == a["data_date"][10:]  # time-of-day / zone untouched
    assert body["revision_label"] == "Feb close"
    assert client.patch(url, json={}).status_code == 422


def test_data_date_edit_is_what_dcma_and_status_read(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a = _upload(client, project.id).json()
    client.patch(f"/projects/{project.id}/schedule-imports/{a['id']}", json={"data_date": "2026-03-01"})

    from app.services.schedule_current import get_current_import

    db_session.expire_all()
    assert get_current_import(db_session, tenant.id, project.id).data_date.date().isoformat() == "2026-03-01"


def _baseline_status(client, project_id):
    return client.get(f"/projects/{project_id}/evm/baseline").json()


def test_baseline_can_be_moved_unlocked_and_restored_exactly(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a, b = _two_imports(client, db_session, project.id)
    first = _baseline_status(client, project.id)["active_baseline"]
    assert first["schedule_import_id"] == a["id"]

    # Move the baseline to the current update (B) — A's baseline is kept as superseded.
    moved = client.post(f"/projects/{project.id}/evm/baseline/from-import/{b['id']}")
    assert moved.status_code == 201
    status = _baseline_status(client, project.id)
    assert status["active_baseline"]["schedule_import_id"] == b["id"]
    assert sorted(x["status"] for x in status["all_baselines"]) == ["active", "superseded"]

    # Unlock: nothing is the baseline any more.
    assert client.delete(f"/projects/{project.id}/evm/baseline/{status['active_baseline']['id']}").status_code == 200
    assert _baseline_status(client, project.id)["has_active"] is False

    # Pointing at A again restores A's original baseline row (same id + label), not a copy.
    restored = client.post(f"/projects/{project.id}/evm/baseline/from-import/{a['id']}")
    assert restored.status_code == 201
    assert restored.json()["baseline_id"] == first["id"]
    assert restored.json()["version_label"] == first["version_label"]
    assert len(_baseline_status(client, project.id)["all_baselines"]) == 2

    # Re-selecting the import that is already the baseline changes nothing.
    again = client.post(f"/projects/{project.id}/evm/baseline/from-import/{a['id']}")
    assert again.status_code == 201 and again.json()["baseline_id"] == first["id"]
    assert len(_baseline_status(client, project.id)["all_baselines"]) == 2


def test_baseline_from_an_earlier_import_uses_its_saved_snapshot(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    base = datetime.now(timezone.utc)
    a = _upload(client, project.id).json()  # auto baseline
    _set_imported_at(db_session, a["id"], base)
    b = _upload(client, project.id).json()
    _set_imported_at(db_session, b["id"], base + timedelta(minutes=1))
    c = _upload(client, project.id).json()  # current
    _set_imported_at(db_session, c["id"], base + timedelta(minutes=2))

    response = client.post(f"/projects/{project.id}/evm/baseline/from-import/{b['id']}")

    assert response.status_code == 201
    active = _baseline_status(client, project.id)["active_baseline"]
    assert active["schedule_import_id"] == b["id"]
    assert active["activity_count"] > 0 and active["total_budget_manhours"] > 0
    # Built from the snapshot, so there are no frozen P6 resources on it.
    resources = client.get(f"/projects/{project.id}/evm/baseline/resources").json()
    assert resources["resource_count"] == 0
    # ...and the variance view works against it.
    assert client.get(f"/projects/{project.id}/evm/baseline/variance").status_code == 200


def test_baseline_from_an_import_without_a_snapshot_is_rejected_and_rolled_back(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a, b = _two_imports(client, db_session, project.id)
    legacy = create_schedule_import(db_session, tenant, project, _admin(db_session), revision_no=9, revision_label="UPD-9")
    before = _baseline_status(client, project.id)["active_baseline"]

    response = client.post(f"/projects/{project.id}/evm/baseline/from-import/{legacy.id}")

    assert response.status_code == 422
    after = _baseline_status(client, project.id)
    assert after["active_baseline"]["id"] == before["id"]  # the supersede was rolled back


def test_activities_table_untouched_by_metadata_edit(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    a = _upload(client, project.id).json()
    before = db_session.query(Activity).filter(Activity.project_id == project.id).count()

    client.patch(f"/projects/{project.id}/schedule-imports/{a['id']}", json={"data_date": "2026-02-01"})

    assert db_session.query(Activity).filter(Activity.project_id == project.id).count() == before
