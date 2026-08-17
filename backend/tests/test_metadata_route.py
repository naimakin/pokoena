from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"

_RSRC_BLOCK = (
    "\n%T\tRSRC\n"
    "%F\trsrc_id\trsrc_name\trsrc_short_name\trsrc_type\tunit_id\tclndr_id\tcurr_id\n"
    "%R\tLAB1\tLaborer\tLAB\tRT_Labor\th\t\tUSD\n"
)

_ACTVCODE_BLOCK = (
    "\n%T\tACTVTYPE\n"
    "%F\tactv_code_type_id\tactv_code_type\tproj_id\n"
    "%R\tCT1\tPhase\t\n"
    "%T\tACTVCODE\n"
    "%F\tactv_code_id\tactv_code_type_id\tactv_code_name\tshort_name\tparent_actv_code_id\tseq_num\n"
    "%R\tCV1\tCT1\tPhase 1\tP1\t\t10\n"
)


def _fixture_with(*blocks: str) -> bytes:
    text = FIXTURE.read_bytes().decode("utf-8")
    return (text + "".join(blocks)).encode("utf-8")


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-metadata-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "metadata-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _login(client):
    client.post("/auth/login", json={"email": "metadata-admin@example.com", "password": "secret123"})


def _import(client, project_id, file_bytes: bytes):
    return client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": ("synthetic_project.xer", file_bytes, "application/octet-stream")},
    )


def test_patch_calendar_updates_name_and_hours(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import(client, project.id, FIXTURE.read_bytes()).status_code == 201

    calendars = client.get(f"/projects/{project.id}/calendars").json()
    assert len(calendars) == 1
    calendar_id = calendars[0]["id"]

    response = client.patch(
        f"/projects/{project.id}/calendars/{calendar_id}", json={"name": "Renamed Calendar", "hours_per_day": 7.5}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed Calendar"
    assert body["hours_per_day"] == 7.5

    refetched = client.get(f"/projects/{project.id}/calendars").json()
    assert refetched[0]["name"] == "Renamed Calendar"


def test_patch_calendar_rejects_id_from_another_project(client, db_session):
    tenant, project = _setup(db_session)
    other_project = create_project(db_session, tenant, name="Other Project")
    _login(client)
    assert _import(client, project.id, FIXTURE.read_bytes()).status_code == 201
    assert _import(client, other_project.id, FIXTURE.read_bytes()).status_code == 201

    other_calendars = client.get(f"/projects/{other_project.id}/calendars").json()
    other_calendar_id = other_calendars[0]["id"]

    response = client.patch(f"/projects/{project.id}/calendars/{other_calendar_id}", json={"name": "Hijacked"})

    assert response.status_code == 400


def test_patch_resource_updates_name(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import(client, project.id, _fixture_with(_RSRC_BLOCK)).status_code == 201

    resources = client.get(f"/projects/{project.id}/resources").json()
    assert len(resources) == 1
    resource_id = resources[0]["id"]

    response = client.patch(f"/projects/{project.id}/resources/{resource_id}", json={"name": "Senior Laborer"})

    assert response.status_code == 200
    assert response.json()["name"] == "Senior Laborer"


def test_patch_activity_code_value_updates_name_and_short_name(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _import(client, project.id, _fixture_with(_ACTVCODE_BLOCK)).status_code == 201

    codes = client.get(f"/projects/{project.id}/activity-codes").json()
    code_value_id = codes["code_values"][0]["id"]

    response = client.patch(
        f"/projects/{project.id}/activity-codes/{code_value_id}",
        json={"name": "Renamed Phase", "short_name": "RP1"},
    )

    assert response.status_code == 200

    refetched = client.get(f"/projects/{project.id}/activity-codes").json()
    assert refetched["code_values"][0]["name"] == "Renamed Phase"
    assert refetched["code_values"][0]["short_name"] == "RP1"
