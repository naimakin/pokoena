import uuid
from datetime import date, datetime, timedelta, timezone

from app.models.change_request import ChangeRequest
from app.models.my_desk import ActivityPin, PersonalNote
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import RecoveryPlan, RecoveryPlanStatus
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.user_tenant_role import TenantRole
from app.services.project_deletion import delete_project
from tests.factories import (
    add_membership,
    create_activity,
    create_project,
    create_schedule_import,
    create_tenant,
    create_update_period,
    create_user,
)
from app.models.project_membership import ProjectMembership


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-desk")
    project = create_project(db_session, tenant, name="Tower", code="TWR")
    admin = create_user(db_session, "desk-admin@example.com", "secret123")
    emp = create_user(db_session, "desk-emp@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    add_membership(db_session, emp, tenant, TenantRole.company_employee)
    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=emp.id))
    db_session.commit()
    return tenant, project, admin, emp


def _login(client, email):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def test_pin_tracks_drift_and_previous_update(client, db_session):
    tenant, project, admin, _ = _setup(db_session)
    upd1 = create_schedule_import(
        db_session, tenant, project, admin, revision_no=1, revision_label="UPD-1",
        snapshot=[{"external_id": "A100", "status": "not_started", "early_finish": "2026-06-01",
                   "total_float_hours": 80.0}],
    )
    upd2 = create_schedule_import(db_session, tenant, project, admin, revision_no=2, revision_label="UPD-2")
    # Same-tick timestamps on a fast clock: make the order explicit.
    upd1.imported_at = upd2.imported_at - timedelta(days=14)
    upd2.is_current = True
    db_session.commit()
    act = create_activity(
        db_session, tenant, project, "A100", early_finish=date(2026, 6, 5), total_float_hours=40.0,
        last_import_id=upd2.id,
    )
    _login(client, "desk-admin@example.com")

    pinned = client.put(f"/my-desk/activities/{act.id}/pin")
    assert pinned.status_code == 200
    body = pinned.json()
    assert body["pinned_finish"] == "2026-06-05"
    assert body["pinned_revision_label"] == "UPD-2"
    assert body["drift_days"] == 0
    assert body["previous_revision_label"] == "UPD-1"
    assert body["previous_finish"] == "2026-06-01"
    assert body["previous_total_float_hours"] == 80.0
    # Pinning twice is a no-op.
    assert client.put(f"/my-desk/activities/{act.id}/pin").json()["id"] == body["id"]

    # The schedule moves on: the pin shows how far it slipped since pinning.
    act.early_finish = date(2026, 6, 12)
    db_session.commit()
    pins = client.get(f"/my-desk/pins?project_id={project.id}").json()
    assert [p["activity_external_id"] for p in pins] == ["A100"]
    assert pins[0]["drift_days"] == 7
    assert pins[0]["activity"]["external_id"] == "A100"

    assert client.get(f"/my-desk/activities/{act.id}").json()["pinned"] is True
    assert client.delete(f"/my-desk/activities/{act.id}/pin").status_code == 204
    assert client.get("/my-desk/pins").json() == []


def test_pins_and_notes_are_private(client, db_session):
    tenant, project, admin, _ = _setup(db_session)
    act = create_activity(db_session, tenant, project, "A200")
    _login(client, "desk-admin@example.com")
    client.put(f"/my-desk/activities/{act.id}/pin")
    note_id = client.post("/my-desk/notes", json={"body": "Chase the rebar mill cert", "activity_id": str(act.id)}).json()["id"]

    _login(client, "desk-emp@example.com")
    assert client.get("/my-desk/pins").json() == []
    assert client.get("/my-desk/notes").json() == []
    desk = client.get(f"/my-desk/activities/{act.id}").json()
    assert desk == {"pinned": False, "notes": []}
    assert client.patch(f"/my-desk/notes/{note_id}", json={"body": "hijack"}).status_code == 404
    assert client.delete(f"/my-desk/notes/{note_id}").status_code == 404


def test_note_crud_with_context_and_reminders(client, db_session):
    tenant, project, admin, _ = _setup(db_session)
    other = create_project(db_session, tenant, name="Depot", code="DPT")
    imp = create_schedule_import(db_session, tenant, project, admin, revision_no=7, revision_label="UPD-7")
    act = create_activity(
        db_session, tenant, project, "A300", early_finish=date(2026, 6, 12), total_float_hours=32.0,
        last_import_id=imp.id,
    )
    _login(client, "desk-admin@example.com")

    on_activity = client.post(
        "/my-desk/notes", json={"body": "Ask about the crane", "activity_id": str(act.id), "remind_on": "2026-10-08"}
    )
    assert on_activity.status_code == 201
    note = on_activity.json()
    assert note["project_id"] == str(project.id)
    assert note["project_code"] == "TWR"
    assert note["activity_external_id"] == "A300"
    assert note["context"]["finish"] == "2026-06-12"
    assert note["context"]["total_float_hours"] == 32.0
    assert note["context"]["revision_label"] == "UPD-7"

    general = client.post("/my-desk/notes", json={"body": "Book site visit"}).json()
    assert general["project_id"] is None
    client.post("/my-desk/notes", json={"body": "Depot only", "project_id": str(other.id)})

    # A project's list carries its own notes and the general ones, reminders first.
    listed = client.get(f"/my-desk/notes?project_id={project.id}").json()
    assert [n["body"] for n in listed] == ["Ask about the crane", "Book site visit"]
    assert len(client.get("/my-desk/notes").json()) == 3

    done = client.patch(f"/my-desk/notes/{note['id']}", json={"done": True, "remind_on": None})
    assert done.json()["done_at"] is not None
    assert done.json()["remind_on"] is None
    # Body-only edits leave the reminder alone.
    client.patch(f"/my-desk/notes/{general['id']}", json={"remind_on": "2026-10-10"})
    kept = client.patch(f"/my-desk/notes/{general['id']}", json={"body": "Book site visit Tue"}).json()
    assert kept["remind_on"] == "2026-10-10"

    listed = client.get(f"/my-desk/notes?project_id={project.id}").json()
    assert [n["body"] for n in listed] == ["Book site visit Tue", "Ask about the crane"]

    assert client.delete(f"/my-desk/notes/{general['id']}").status_code == 204
    assert client.post("/my-desk/notes", json={"body": "   "}).status_code == 422


def test_inbox_rolls_up_what_waits_on_each_role(client, db_session):
    tenant, project, admin, emp = _setup(db_session)
    org = SubcontractorOrganization(id=uuid.uuid4(), tenant_id=tenant.id, name="Steel Co", discipline="Structure")
    db_session.add(org)
    db_session.flush()
    db_session.add(
        ProjectScope(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, name="Steel",
                     discipline="Structure", subcontractor_org_id=org.id)
    )
    period = create_update_period(db_session, tenant, project, number=3)
    for code, status, author in (
        ("A1", RecoveryPlanStatus.submitted, emp),
        ("A2", RecoveryPlanStatus.submitted, emp),
        ("A3", RecoveryPlanStatus.needs_revision, emp),
    ):
        db_session.add(
            RecoveryPlan(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, activity_external_id=code,
                         status=status, created_by_user_id=author.id)
        )
    db_session.add(
        ChangeRequest(id=uuid.uuid4(), tenant_id=tenant.id, update_period_id=period.id, requested_by_user_id=emp.id,
                      field_changed="lag", before_value="0", after_value="5", justification="Cure time")
    )
    db_session.commit()

    _login(client, "desk-admin@example.com")
    inbox = client.get("/my-desk/inbox").json()
    by_kind = {i["kind"]: i for i in inbox}
    assert by_kind["recovery_review"]["count"] == 2
    assert by_kind["recovery_review"]["detail"] == "A1, A2"
    assert by_kind["flag_review"]["count"] == 1
    assert by_kind["update_period"]["title"] == "UPD-3 is open"
    assert by_kind["update_period"]["detail"] == "1 of 1 subcontractors haven't submitted"
    assert "recovery_revision" not in by_kind  # not the author

    _login(client, "desk-emp@example.com")
    kinds = {i["kind"] for i in client.get(f"/my-desk/inbox?project_id={project.id}").json()}
    assert kinds == {"recovery_revision", "update_period"}


def test_overdue_update_period_is_critical(client, db_session):
    tenant, project, _, _ = _setup(db_session)
    period = create_update_period(db_session, tenant, project, number=4)
    period.deadline_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    _login(client, "desk-admin@example.com")
    item = client.get("/my-desk/inbox").json()[0]
    assert item["tone"] == "crit"
    assert item["title"] == "UPD-4 is past its deadline"


def test_suggestions_skip_pinned_and_quiet_work(client, db_session):
    tenant, project, _, _ = _setup(db_session)
    neg = create_activity(db_session, tenant, project, "N1", total_float_hours=-16.0)
    create_activity(db_session, tenant, project, "C1", total_float_hours=0.0, is_critical=True)
    create_activity(db_session, tenant, project, "Q1", total_float_hours=400.0, planned_start=date(2030, 1, 1))
    _login(client, "desk-admin@example.com")

    suggestions = client.get(f"/my-desk/suggestions?project_id={project.id}").json()
    reasons = {s["activity"]["external_id"]: s["reason"] for s in suggestions}
    assert reasons == {"N1": "Negative float", "C1": "Critical"}

    client.put(f"/my-desk/activities/{neg.id}/pin")
    codes = [s["activity"]["external_id"] for s in client.get(f"/my-desk/suggestions?project_id={project.id}").json()]
    assert codes == ["C1"]


def test_access_follows_project_visibility(client, db_session):
    tenant, project, admin, _ = _setup(db_session)
    hidden = create_project(db_session, tenant, name="Hidden", code="HID")
    act = create_activity(db_session, tenant, hidden, "H1")
    _login(client, "desk-emp@example.com")
    assert client.get(f"/my-desk/pins?project_id={hidden.id}").status_code == 403
    assert client.put(f"/my-desk/activities/{act.id}/pin").status_code == 403
    assert client.post("/my-desk/notes", json={"body": "x", "project_id": str(hidden.id)}).status_code == 403

    sub = create_user(db_session, "desk-sub@example.com", "secret123")
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    _login(client, "desk-sub@example.com")
    assert client.get("/my-desk/notes").status_code == 403


def test_project_deletion_takes_pins_and_notes(db_session):
    tenant, project, admin, _ = _setup(db_session)
    db_session.add(ActivityPin(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=admin.id,
                               activity_external_id="A1", activity_name="A1"))
    db_session.add(PersonalNote(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=admin.id,
                                body="gone with the project"))
    db_session.add(PersonalNote(id=uuid.uuid4(), tenant_id=tenant.id, user_id=admin.id, body="stays"))
    db_session.commit()
    delete_project(db_session, tenant.id, project.id)
    db_session.commit()
    assert db_session.query(ActivityPin).count() == 0
    assert [n.body for n in db_session.query(PersonalNote).all()] == ["stays"]
