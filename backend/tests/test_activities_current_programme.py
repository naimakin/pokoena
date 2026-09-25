"""GET /activities lists the current programme, not everything ever imported.

An .xer import prunes WBS nodes that are no longer in the file but deliberately
keeps activity rows, because they carry subcontractor progress and Poko's own
annotations. Those leftovers used to come back from this endpoint with a
wbs_path pointing at a deleted node, so every grid filed them under "Ungrouped"
and they inflated the project's activity counts. See routes/activities.py.
"""

from app.models.user_tenant_role import TenantRole
from tests.factories import (
    add_membership,
    create_activity,
    create_project,
    create_schedule_import,
    create_tenant,
    create_user,
)


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-current-prog")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "prog-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, admin


def _login(client):
    client.post("/auth/login", json={"email": "prog-admin@example.com", "password": "secret123"})


def _codes(client, project_id) -> set[str]:
    response = client.get(f"/activities?project_id={project_id}")
    assert response.status_code == 200
    return {a["external_id"] for a in response.json()}


def test_activity_dropped_by_a_later_import_is_not_listed(client, db_session):
    tenant, project, admin = _setup(db_session)
    old = create_schedule_import(db_session, tenant, project, admin, revision_label="UPD-1")
    new = create_schedule_import(db_session, tenant, project, admin, revision_label="UPD-2")
    new.is_current = True
    db_session.commit()

    create_activity(db_session, tenant, project, "KEPT", last_import_id=new.id)
    create_activity(db_session, tenant, project, "DROPPED", last_import_id=old.id)
    _login(client)

    assert _codes(client, project.id) == {"KEPT"}


def test_user_created_activity_survives_without_an_import(client, db_session):
    # last_import_id IS NULL means the activity was created by a user, or its
    # import was deleted (routes/schedule_imports.py nulls the column) — either
    # way it isn't a leftover from a superseded programme.
    tenant, project, admin = _setup(db_session)
    current = create_schedule_import(db_session, tenant, project, admin, revision_label="UPD-1")
    current.is_current = True
    db_session.commit()

    create_activity(db_session, tenant, project, "FROM-XER", last_import_id=current.id)
    create_activity(db_session, tenant, project, "BY-HAND")
    _login(client)

    assert _codes(client, project.id) == {"FROM-XER", "BY-HAND"}


def test_activities_are_all_listed_when_the_project_has_no_imports(client, db_session):
    # Nothing to compare against, so filtering would hide the whole project.
    tenant, project, _admin = _setup(db_session)
    create_activity(db_session, tenant, project, "A1")
    create_activity(db_session, tenant, project, "A2")
    _login(client)

    assert _codes(client, project.id) == {"A1", "A2"}
