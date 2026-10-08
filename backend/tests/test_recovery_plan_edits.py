"""Recovery plans stay editable after submit / acknowledgement, owners and
@mentions notify through My Desk, and the slip report takes a From / To choice."""

import uuid
from datetime import date

from app.models.baseline import Baseline, BaselineStatus
from app.models.mention import Mention, MentionKind
from app.models.project_membership import ProjectMembership
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user_tenant_role import ProjectRole, TenantRole
from tests.factories import (
    add_membership,
    create_activity,
    create_project,
    create_project_scope,
    create_schedule_import,
    create_tenant,
    create_update_period,
    create_user,
)

PW = "secret123"


def _snap(external_id, finish):
    return {
        "external_id": external_id, "p6_task_id": None, "name": external_id, "wbs_path": None,
        "planned_finish": finish, "early_finish": None, "actual_finish": None,
        "is_critical": False, "is_longest_path": False,
        "total_float_hours": None, "status": "in_progress", "percent_complete": 20,
    }


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
    tenant = create_tenant(db, name="Edit", slug=f"rpe-{uuid.uuid4().hex[:6]}")
    project = create_project(db, tenant)
    steel = create_project_scope(db, tenant, project, name="Steel")
    civil = create_project_scope(db, tenant, project, name="Civil")
    p = {
        "admin": _person(db, tenant, project, "rpe-admin@example.com", "Ali Admin", role=TenantRole.company_admin),
        "pm": _person(db, tenant, project, "rpe-pm@example.com", "Pia Manager", roles=[ProjectRole.project_manager]),
        "pm2": _person(db, tenant, project, "rpe-pm2@example.com", "Per Planner", roles=[ProjectRole.delivery_team]),
        "viewer": _person(db, tenant, project, "rpe-view@example.com", "Vic Viewer", roles=[ProjectRole.viewer]),
        "outsider": _person(db, tenant, project, "rpe-out@example.com", "Otto Outsider",
                            roles=[ProjectRole.delivery_team], member=False),
        "sub": _person(db, tenant, project, "rpe-sub@example.com", "Sam Steel", role=TenantRole.subcontractor),
        "sub2": _person(db, tenant, project, "rpe-sub2@example.com", "Cem Civil", role=TenantRole.subcontractor),
    }
    for key, scope in (("sub", steel), ("sub2", civil)):
        db.add(SubcontractorScopeAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, user_id=p[key].id, project_scope_id=scope.id,
            assigned_by_user_id=p["admin"].id,
        ))
    create_activity(db, tenant, project, "SELF")
    create_activity(db, tenant, project, "SUB1", project_scope_id=steel.id)
    imports = {
        "upd1": create_schedule_import(db, tenant, project, p["admin"], revision_no=1, revision_label="UPD-1",
                                       snapshot=[_snap("SELF", "2026-06-01"), _snap("SUB1", "2026-06-01")]),
        "upd2": create_schedule_import(db, tenant, project, p["admin"], revision_no=2, revision_label="UPD-2",
                                       snapshot=[_snap("SELF", "2026-06-10"), _snap("SUB1", "2026-06-05")]),
        "upd3": create_schedule_import(db, tenant, project, p["admin"], revision_no=3, revision_label="UPD-3",
                                       snapshot=[_snap("SELF", "2026-06-20"), _snap("SUB1", "2026-06-25")]),
    }
    db.commit()
    return tenant, project, p, imports


def _tag(user):
    return f"@[{user.full_name}](user:{user.id})"


def _base(project):
    return f"/projects/{project.id}/recovery-plan/plans"


def _accepted_self_plan(client, project):
    """PM writes + submits a self-perform plan, PM2 acknowledges it."""
    base = _base(project)
    _login(client, "rpe-pm@example.com")
    plan = client.post(base, json={"activity_external_id": "SELF", "summary": "Late steel"}).json()
    item = client.post(f"{base}/{plan['id']}/items", json={"action": "Night shift"}).json()
    assert client.post(f"{base}/{plan['id']}/submit").status_code == 200
    _login(client, "rpe-pm2@example.com")
    assert client.post(f"{base}/{plan['id']}/review", json={"decision": "accept"}).json()["status"] == "accepted"
    return plan["id"], item["id"]


# --- editing after submit / acknowledgement --------------------------------


def test_edit_after_submit_and_acknowledge_keeps_status_and_records_editor(client, db_session):
    _tenant, project, p, _ = _world(db_session)
    base = _base(project)
    _login(client, "rpe-pm@example.com")
    plan = client.post(base, json={"activity_external_id": "SELF"}).json()
    assert plan["can_edit"] is True
    item = client.post(f"{base}/{plan['id']}/items", json={"action": "Night shift"}).json()
    client.post(f"{base}/{plan['id']}/submit")

    # Edited while submitted: still submitted, flagged.
    r = client.patch(f"{base}/{plan['id']}", json={"summary": "Steel arrived late"})
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"
    assert r.json()["edited_after"] == "submission"
    assert r.json()["edited_by_name"] == "Pia Manager"

    _login(client, "rpe-pm2@example.com")
    client.post(f"{base}/{plan['id']}/review", json={"decision": "accept"})
    assert client.get(f"{base}/{plan['id']}").json()["edited_after"] is None  # acknowledged after the edit

    _login(client, "rpe-pm@example.com")
    for body in ({"action": "Two night shifts"}, {"target_date": "2026-07-01"}, {"status": "in_progress"}):
        assert client.patch(f"{base}/{plan['id']}/items/{item['id']}", json=body).status_code == 200
    extra = client.post(f"{base}/{plan['id']}/items", json={"action": "Extra crane"})
    assert extra.status_code == 201
    assert client.delete(f"{base}/{plan['id']}/items/{extra.json()['id']}").status_code == 204

    detail = client.get(f"{base}/{plan['id']}").json()
    assert detail["status"] == "accepted"
    assert detail["edited_after"] == "acknowledgement"
    assert detail["edited_by_user_id"] == str(p["pm"].id)
    assert detail["reviewed_by_name"] == "Per Planner"
    assert [i["action"] for i in detail["items"]] == ["Two night shifts"]
    assert detail["items"][0]["target_date"] == "2026-07-01"

    # Re-submitting an acknowledged plan is still refused.
    assert client.post(f"{base}/{plan['id']}/submit").status_code == 409


def test_progress_tick_alone_does_not_flag_an_edit(client, db_session):
    _tenant, project, _p, _ = _world(db_session)
    plan_id, item_id = _accepted_self_plan(client, project)
    _login(client, "rpe-pm2@example.com")
    r = client.patch(f"{_base(project)}/{plan_id}/items/{item_id}", json={"status": "done"})
    assert r.status_code == 200
    assert client.get(f"{_base(project)}/{plan_id}").json()["edited_after"] is None
    # Self-perform work belongs to the company team: anyone who manages progress
    # may rewrite it too, and that does flag the plan.
    assert client.patch(f"{_base(project)}/{plan_id}/items/{item_id}", json={"action": "x"}).status_code == 200
    detail = client.get(f"{_base(project)}/{plan_id}").json()
    assert detail["edited_after"] == "acknowledgement" and detail["edited_by_name"] == "Per Planner"


def test_company_ticks_progress_on_an_acknowledged_subcontractor_plan(client, db_session):
    tenant, project, _p, _ = _world(db_session)
    create_update_period(db_session, tenant, project, number=3)
    base = _base(project)
    _login(client, "rpe-sub@example.com")
    plan = client.post(base, json={"activity_external_id": "SUB1"}).json()
    item = client.post(f"{base}/{plan['id']}/items", json={"action": "Extra welders"}).json()
    client.post(f"{base}/{plan['id']}/submit")
    _login(client, "rpe-pm@example.com")
    url = f"{base}/{plan['id']}/items/{item['id']}"
    assert client.patch(url, json={"status": "done"}).status_code == 403  # not acknowledged yet
    client.post(f"{base}/{plan['id']}/review", json={"decision": "accept"})
    assert client.patch(url, json={"status": "done"}).status_code == 200
    assert client.patch(url, json={"action": "rewritten"}).status_code == 403  # the subcontractor's words
    _login(client, "rpe-view@example.com")
    assert client.patch(url, json={"status": "open"}).status_code == 403


def test_who_may_edit(client, db_session):
    tenant, project, _p, _ = _world(db_session)
    create_update_period(db_session, tenant, project, number=3)
    base = _base(project)

    _login(client, "rpe-sub@example.com")
    sub_plan = client.post(base, json={"activity_external_id": "SUB1"}).json()
    assert sub_plan["can_edit"] is True

    # Another subcontractor's scope: can't even see it, let alone edit.
    _login(client, "rpe-sub2@example.com")
    assert client.patch(f"{base}/{sub_plan['id']}", json={"summary": "x"}).status_code == 403
    assert client.post(f"{base}/{sub_plan['id']}/items", json={"action": "x"}).status_code == 403

    # The company doesn't write a subcontractor's plan.
    _login(client, "rpe-admin@example.com")
    assert client.patch(f"{base}/{sub_plan['id']}", json={"summary": "x"}).status_code == 403
    assert client.get(f"{base}/{sub_plan['id']}").json()["can_edit"] is False

    # A self-perform plan needs edit_progress: a Viewer can't edit it.
    plan_id, _item = _accepted_self_plan(client, project)
    _login(client, "rpe-view@example.com")
    assert client.patch(f"{base}/{plan_id}", json={"summary": "x"}).status_code == 403
    assert client.get(f"{base}/{plan_id}").json()["can_edit"] is False


# --- owners and @mentions --------------------------------------------------


def _mentions(db, user, kind=None):
    q = db.query(Mention).filter(Mention.mentioned_user_id == user.id)
    if kind:
        q = q.filter(Mention.kind == kind)
    return q.all()


def test_owner_must_see_the_activity_and_is_notified_once(client, db_session):
    _tenant, project, p, _ = _world(db_session)
    base = _base(project)
    _login(client, "rpe-pm@example.com")
    plan = client.post(base, json={"activity_external_id": "SELF"}).json()

    people = client.get(f"{base}/{plan['id']}/people?include_self=true").json()
    names = {x["full_name"] for x in people}
    assert {"Pia Manager", "Ali Admin", "Per Planner"} <= names
    assert "Otto Outsider" not in names and "Sam Steel" not in names  # not a member / not this scope
    assert "Pia Manager" not in {x["full_name"] for x in client.get(f"{base}/{plan['id']}/people").json()}

    bad = client.post(f"{base}/{plan['id']}/items", json={"action": "x", "owner_user_id": str(p["outsider"].id)})
    assert bad.status_code == 400
    item = client.post(f"{base}/{plan['id']}/items", json={"action": "Crane", "owner_user_id": str(p["pm2"].id)})
    assert item.status_code == 201
    assert item.json()["owner_name"] == "Per Planner" and item.json()["owner_user_id"] == str(p["pm2"].id)
    assert len(_mentions(db_session, p["pm2"], MentionKind.recovery_owner)) == 1

    # Same owner saved again: no second notification.
    url = f"{base}/{plan['id']}/items/{item.json()['id']}"
    client.patch(url, json={"owner_user_id": str(p["pm2"].id)})
    assert len(_mentions(db_session, p["pm2"], MentionKind.recovery_owner)) == 1
    assert client.patch(url, json={"owner_user_id": str(p["outsider"].id)}).status_code == 400

    # Free text clears the person; assigning yourself notifies nobody.
    r = client.patch(url, json={"owner_name": "Crane hire Ltd"}).json()
    assert r["owner_user_id"] is None and r["owner_name"] == "Crane hire Ltd"
    client.patch(url, json={"owner_user_id": str(p["pm"].id)})
    assert _mentions(db_session, p["pm"]) == []


def test_mentions_in_root_cause_and_actions_notify_once(client, db_session):
    _tenant, project, p, _ = _world(db_session)
    base = _base(project)
    _login(client, "rpe-pm@example.com")
    plan = client.post(base, json={"activity_external_id": "SELF"}).json()

    text = f"Steel late, ask {_tag(p['admin'])} and {_tag(p['outsider'])}"
    client.patch(f"{base}/{plan['id']}", json={"summary": text})
    client.patch(f"{base}/{plan['id']}", json={"summary": text + " today"})  # same people, edited around
    assert len(_mentions(db_session, p["admin"], MentionKind.recovery_root_cause)) == 1
    assert _mentions(db_session, p["outsider"]) == []  # can't see the activity: stays plain text

    client.patch(f"{base}/{plan['id']}", json={"summary": f"{text} cc {_tag(p['pm2'])}"})
    assert len(_mentions(db_session, p["admin"], MentionKind.recovery_root_cause)) == 1
    assert len(_mentions(db_session, p["pm2"], MentionKind.recovery_root_cause)) == 1

    item = client.post(f"{base}/{plan['id']}/items", json={"action": f"Call {_tag(p['admin'])}"}).json()
    client.patch(f"{base}/{plan['id']}/items/{item['id']}", json={"action": f"Call {_tag(p['admin'])} now"})
    assert len(_mentions(db_session, p["admin"], MentionKind.recovery_action)) == 1

    # The tagged person's My Desk lists it, linking to the plan's row.
    _login(client, "rpe-admin@example.com")
    rows = client.get("/my-desk/mentions").json()
    kinds = {r["kind"] for r in rows}
    assert kinds == {MentionKind.recovery_root_cause, MentionKind.recovery_action}
    root = next(r for r in rows if r["kind"] == MentionKind.recovery_root_cause)
    assert root["recovery_plan_id"] == plan["id"]
    assert root["event_id"] is None
    assert root["author_name"] == "Pia Manager"
    assert "cc" in root["body"]
    assert root["href"].startswith("/recovery-plan?") and "activity=SELF" in root["href"]
    assert client.get("/my-desk/mentions/count").json()["unread"] == 2


# --- From / To comparison ---------------------------------------------------


def test_default_comparison_is_latest_two_updates(client, db_session):
    _tenant, project, _p, imports = _world(db_session)
    _login(client, "rpe-admin@example.com")
    body = client.get(f"/projects/{project.id}/recovery-plan").json()
    assert body["comparison_basis"] == "previous_upd" and body["is_default"] is True
    assert body["from_import"]["id"] == str(imports["upd2"].id)
    assert body["to_import"]["id"] == str(imports["upd3"].id)
    assert body["baseline"] is None


def test_chosen_programs(client, db_session):
    tenant, project, p, imports = _world(db_session)
    url = f"/projects/{project.id}/recovery-plan"
    _login(client, "rpe-admin@example.com")

    body = client.get(f"{url}?from_import_id={imports['upd1'].id}&to_import_id={imports['upd2'].id}").json()
    assert body["comparison_basis"] == "custom" and body["is_default"] is False
    assert {r["external_id"]: r["slip_days"] for r in body["slipped"]} == {"SELF": 9, "SUB1": 4}

    # To alone compares against the update before it.
    body = client.get(f"{url}?to_import_id={imports['upd2'].id}").json()
    assert body["from_import"]["id"] == str(imports["upd1"].id)

    # Choosing exactly the default pair reads as the default.
    body = client.get(f"{url}?from_import_id={imports['upd2'].id}&to_import_id={imports['upd3'].id}").json()
    assert body["is_default"] is True and body["comparison_basis"] == "previous_upd"

    assert client.get(f"{url}?from_import_id={imports['upd2'].id}&to_import_id={imports['upd2'].id}").status_code == 400
    assert client.get(f"{url}?from_baseline=true").status_code == 400  # no active baseline yet

    other_tenant = create_tenant(db_session, name="Other", slug=f"rpe-o-{uuid.uuid4().hex[:6]}")
    other_project = create_project(db_session, other_tenant)
    foreign = create_schedule_import(db_session, other_tenant, other_project, p["admin"], revision_no=1,
                                     revision_label="UPD-1", snapshot=[_snap("SELF", "2026-01-01")])
    other_here = create_project(db_session, tenant)
    same_tenant_other_project = create_schedule_import(db_session, tenant, other_here, p["admin"], revision_no=1,
                                                       revision_label="UPD-1", snapshot=[])
    assert client.get(f"{url}?from_import_id={foreign.id}").status_code == 404
    assert client.get(f"{url}?to_import_id={same_tenant_other_project.id}").status_code == 404


def test_from_baseline(client, db_session):
    tenant, project, p, imports = _world(db_session)
    db_session.add(Baseline(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, schedule_import_id=imports["upd1"].id,
        version_label="Target-1", total_budget_manhours=100.0, target_start_date=date(2026, 1, 1),
        target_end_date=date(2026, 12, 31), status=BaselineStatus.active, activity_count=2,
    ))
    db_session.commit()
    url = f"/projects/{project.id}/recovery-plan"
    _login(client, "rpe-admin@example.com")

    assert client.get(url).json()["baseline"]["label"] == "Target-1"
    body = client.get(f"{url}?from_baseline=true").json()
    assert body["comparison_basis"] == "baseline" and body["from_baseline"] is True
    assert body["from_import"]["id"] == str(imports["upd1"].id)
    assert {r["external_id"]: r["slip_days"] for r in body["slipped"]} == {"SELF": 19, "SUB1": 24}
    assert client.get(f"{url}?from_baseline=true&from_import_id={imports['upd2'].id}").status_code == 400


def test_plan_records_the_comparison_it_was_raised_against(client, db_session):
    _tenant, project, _p, imports = _world(db_session)
    _login(client, "rpe-admin@example.com")
    r = client.post(_base(project), json={
        "activity_external_id": "SELF",
        "from_import_id": str(imports["upd1"].id),
        "to_import_id": str(imports["upd2"].id),
    })
    assert r.status_code == 201
    plan = r.json()
    assert plan["from_import_id"] == str(imports["upd1"].id) and plan["to_import_id"] == str(imports["upd2"].id)
    assert plan["from_label"] == "UPD-1" and plan["to_label"] == "UPD-2"
    assert plan["slip_days_at_creation"] == 9
