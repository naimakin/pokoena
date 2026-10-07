"""@mentions in activity comments: who can be tagged, what's stored, and the
tagged person's My Desk notifications."""

import uuid

from app.models.mention import Mention
from app.models.project_membership import ProjectMembership
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user_tenant_role import ProjectRole, TenantRole
from app.services.mentions import mentioned_ids, plain_text
from tests.factories import (
    add_membership,
    create_activity,
    create_project,
    create_project_scope,
    create_tenant,
    create_user,
)

PW = "secret123"


def _login(client, email):
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 200


def _person(db, tenant, project, email, name, role=TenantRole.company_employee, roles=None, member=True):
    user = create_user(db, email, PW)
    user.full_name = name
    add_membership(db, user, tenant, role, project_roles=roles)
    if member and role == TenantRole.company_employee:
        db.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    db.commit()
    return user


def _world(db):
    tenant = create_tenant(db, name="Ment", slug=f"ment-{uuid.uuid4().hex[:6]}")
    project = create_project(db, tenant, code="HER01")
    scope = create_project_scope(db, tenant, project, name="MEP")
    other_scope = create_project_scope(db, tenant, project, name="Civil")
    act = create_activity(db, tenant, project, "A-100", name="Pull LV cables", project_scope_id=scope.id)
    people = {
        "admin": _person(db, tenant, project, "m-admin@example.com", "Ali Admin", role=TenantRole.company_admin),
        "pm": _person(db, tenant, project, "m-pm@example.com", "Pia Manager", roles=[ProjectRole.project_manager]),
        "dash": _person(db, tenant, project, "m-dash@example.com", "Dan Dashboard", roles=[ProjectRole.dashboard_viewer]),
        "outsider": _person(db, tenant, project, "m-out@example.com", "Otto Outsider",
                            roles=[ProjectRole.delivery_team], member=False),
        "sub": _person(db, tenant, project, "m-sub@example.com", "Sam Site", role=TenantRole.subcontractor),
        "sub2": _person(db, tenant, project, "m-sub2@example.com", "Cem Civil", role=TenantRole.subcontractor),
    }
    for key, s in (("sub", scope), ("sub2", other_scope)):
        db.add(SubcontractorScopeAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, user_id=people[key].id, project_scope_id=s.id,
            assigned_by_user_id=people["admin"].id,
        ))
    db.commit()
    return tenant, project, act, people


def _tag(user):
    return f"@[{user.full_name}](user:{user.id})"


def test_tokens_parse_and_render():
    a, b = uuid.uuid4(), uuid.uuid4()
    body = f"Hi @[Ana Demir](user:{a}) and @[Bo](user:{b}), also @[Ana Demir](user:{a}) and @plain"
    assert mentioned_ids(body) == [a, b]
    assert plain_text(body) == "Hi @Ana Demir and @Bo, also @Ana Demir and @plain"


def test_mentionable_people_are_who_can_see_the_activity(client, db_session):
    _tenant, _project, act, p = _world(db_session)
    _login(client, "m-pm@example.com")

    rows = client.get(f"/activities/{act.id}/mentionable-users").json()

    names = {r["full_name"] for r in rows}
    assert names == {"Ali Admin", "Sam Site"}  # not self, a Dashboard Viewer, a non-member, another scope
    assert all(set(r) == {"id", "full_name", "label"} for r in rows)  # never an email
    assert client.get(f"/activities/{act.id}/mentionable-users?q=sam").json()[0]["full_name"] == "Sam Site"


def test_comment_mentions_only_valid_people_and_notifies_them(client, db_session):
    _tenant, project, act, p = _world(db_session)
    _login(client, "m-pm@example.com")
    body = f"{_tag(p['sub'])} permit is blocked, {_tag(p['dash'])} {_tag(p['outsider'])} {_tag(p['pm'])}"

    r = client.post(f"/activities/{act.id}/comments", json={"body": body})

    assert r.status_code == 201, r.text
    assert r.json()["event_id"]
    stored = db_session.query(Mention).all()
    assert [m.mentioned_user_id for m in stored] == [p["sub"].id]  # the rest ignored, self too

    _login(client, "m-sub@example.com")
    assert client.get("/my-desk/mentions/count").json() == {"unread": 1}
    mentions = client.get("/my-desk/mentions?unread=true").json()
    assert mentions[0]["activity_external_id"] == "A-100"
    assert mentions[0]["author_name"] == "Pia Manager"
    assert mentions[0]["project_code"] == "HER01"
    assert "permit is blocked" in mentions[0]["body"]

    assert client.post(f"/my-desk/mentions/{mentions[0]['id']}/read").json() == {"unread": 0}
    assert client.get("/my-desk/mentions?unread=true").json() == []


def test_mentions_are_private_and_show_in_the_inbox(client, db_session):
    _tenant, project, act, p = _world(db_session)
    _login(client, "m-admin@example.com")
    client.post(f"/activities/{act.id}/comments", json={"body": f"{_tag(p['pm'])} look"})
    client.post(f"/activities/{act.id}/comments", json={"body": f"{_tag(p['pm'])} and again"})

    _login(client, "m-pm@example.com")
    inbox = {i["kind"]: i for i in client.get("/my-desk/inbox").json()}
    assert inbox["mention"]["count"] == 2 and inbox["mention"]["title"] == "2 new mentions"
    mine = client.get("/my-desk/mentions").json()

    _login(client, "m-sub@example.com")
    assert client.get("/my-desk/mentions").json() == []
    assert client.post(f"/my-desk/mentions/{mine[0]['id']}/read").status_code == 404

    _login(client, "m-pm@example.com")
    assert client.post("/my-desk/mentions/read-all").json() == {"unread": 0}
    assert "mention" not in {i["kind"] for i in client.get("/my-desk/inbox").json()}


def test_subcontractor_cannot_list_people_outside_their_scope(client, db_session):
    tenant, project, _act, _p = _world(db_session)
    civil_act = create_activity(db_session, tenant, project, "C-1",
                                project_scope_id=create_project_scope(db_session, tenant, project, name="X").id)
    _login(client, "m-sub@example.com")

    assert client.get(f"/activities/{civil_act.id}/mentionable-users").status_code == 403


def test_one_activity_can_be_fetched_within_scope(client, db_session):
    tenant, project, act, _p = _world(db_session)
    other = create_activity(db_session, tenant, project, "Z-9")
    _login(client, "m-sub@example.com")

    assert client.get(f"/activities/{act.id}").json()["external_id"] == "A-100"
    assert client.get(f"/activities/{other.id}").status_code == 403
