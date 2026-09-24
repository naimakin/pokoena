"""The Activity modal's History tab: user edits + comments from activity_events,
merged with programme-driven movement derived from consecutive import snapshots."""

from pathlib import Path

from app.models.activity import Activity
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-act-history")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "history-admin@example.com", "secret123")
    # No UpdatePeriod: a company_admin's progress edits aren't period-gated
    # (see _authorize_progress_edit), and the period flow has its own tests.
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, admin


def _login(client):
    client.post("/auth/login", json={"email": "history-admin@example.com", "password": "secret123"})


def _upload(client, project_id, content: bytes, name: str):
    return client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": (name, content, "application/octet-stream")},
    )


def _activity(db_session, project, external_id="A100"):
    return (
        db_session.query(Activity)
        .filter(Activity.project_id == project.id, Activity.external_id == external_id)
        .one()
    )


def test_history_is_empty_before_anything_happens(client, db_session):
    _tenant, project = _setup(db_session)[:2]
    _login(client)
    assert _upload(client, project.id, FIXTURE.read_bytes(), "p.xer").status_code == 201

    activity = _activity(db_session, project)
    response = client.get(f"/activities/{activity.id}/history")

    assert response.status_code == 200
    assert response.json() == []


def test_edit_records_one_entry_per_changed_field(client, db_session):
    _tenant, project = _setup(db_session)[:2]
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), "p.xer")
    activity = _activity(db_session, project)

    patch = client.patch(
        f"/activities/{activity.id}",
        json={"actual_start": "2026-02-02", "is_important": True},
    )
    assert patch.status_code == 200

    history = client.get(f"/activities/{activity.id}/history").json()
    by_field = {item["field"]: item for item in history if item["kind"] == "change"}

    # actual_start and is_important were set directly; status is derived from the
    # actual date, and the timeline reports that derivation too.
    assert by_field["actual_start"]["old_value"] is None
    assert by_field["actual_start"]["new_value"] == "2026-02-02"
    assert by_field["is_important"]["new_value"] == "true"
    assert by_field["status"]["new_value"] == "in_progress"
    assert all(item["actor_name"] == "history-admin@example.com" or item["actor_name"] for item in history)


def test_unchanged_fields_are_not_recorded(client, db_session):
    _tenant, project = _setup(db_session)[:2]
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), "p.xer")
    activity = _activity(db_session, project)

    client.patch(f"/activities/{activity.id}", json={"is_important": True})
    client.patch(f"/activities/{activity.id}", json={"is_important": True})

    changes = [i for i in client.get(f"/activities/{activity.id}/history").json() if i["kind"] == "change"]
    assert [c["field"] for c in changes] == ["is_important"]


def test_comment_lands_in_the_timeline(client, db_session):
    _tenant, project = _setup(db_session)[:2]
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), "p.xer")
    activity = _activity(db_session, project)

    created = client.post(f"/activities/{activity.id}/comments", json={"body": "Blocked on the permit"})
    assert created.status_code == 201
    assert created.json()["body"] == "Blocked on the permit"

    history = client.get(f"/activities/{activity.id}/history").json()
    comments = [i for i in history if i["kind"] == "comment"]
    assert len(comments) == 1
    assert comments[0]["body"] == "Blocked on the permit"
    assert comments[0]["actor_name"]


def test_a_second_import_shows_up_as_version_movement(client, db_session):
    _tenant, project = _setup(db_session)[:2]
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), "upd1.xer")

    # Same programme, every date a month later: the snapshot diff should report it.
    shifted = FIXTURE.read_bytes().replace(b"2026-01-05", b"2026-02-05")
    assert _upload(client, project.id, shifted, "upd2.xer").status_code == 201

    activity = _activity(db_session, project)
    history = client.get(f"/activities/{activity.id}/history").json()
    versions = [i for i in history if i["kind"] == "version"]

    assert versions, "expected date movement between the two imports"
    assert all(v["revision_label"] for v in versions)
    assert all(v["old_value"] != v["new_value"] for v in versions)


def test_annotations_survive_a_reimport(client, db_session):
    """is_important/tags/notes are Poko's, not P6's — a re-import overwrites the
    schedule fields and must leave these alone."""
    _tenant, project = _setup(db_session)[:2]
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), "upd1.xer")
    activity = _activity(db_session, project)

    client.patch(
        f"/activities/{activity.id}",
        json={"is_important": True, "tags": ["permit", "long-lead"], "notes": "On hold"},
    )

    shifted = FIXTURE.read_bytes().replace(b"2026-01-05", b"2026-02-05")
    assert _upload(client, project.id, shifted, "upd2.xer").status_code == 201

    db_session.expire_all()
    after = _activity(db_session, project)
    assert after.is_important is True
    assert after.tags == ["permit", "long-lead"]
    assert after.notes == "On hold"


def test_subcontractor_cannot_read_another_scopes_activity_history(client, db_session):
    tenant, project, _admin = _setup(db_session)
    _login(client)
    _upload(client, project.id, FIXTURE.read_bytes(), "p.xer")
    activity = _activity(db_session, project)

    sub = create_user(db_session, "history-sub@example.com", "secret123")
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    client.post("/auth/login", json={"email": "history-sub@example.com", "password": "secret123"})

    assert client.get(f"/activities/{activity.id}/history").status_code in (403, 404)
