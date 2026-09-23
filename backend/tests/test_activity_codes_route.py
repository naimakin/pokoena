from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"

_ACTIVITY_CODE_BLOCKS = (
    "\n%T\tACTVTYPE\n"
    "%F\tactv_code_type_id\tactv_code_type\tproj_id\n"
    "%R\tCT1\tPhase\t\n"
    "%T\tACTVCODE\n"
    "%F\tactv_code_id\tactv_code_type_id\tactv_code_name\tshort_name\tparent_actv_code_id\tseq_num\n"
    "%R\tCV1\tCT1\tPhase 1\tP1\t\t10\n"
    "%T\tTASKACTV\n"
    "%F\ttask_id\tactv_code_type_id\tactv_code_id\n"
    "%R\t1001\tCT1\tCV1\n"  # task_id "1001" is A100 in the synthetic fixture
)


def _fixture_with_activity_codes() -> bytes:
    text = FIXTURE.read_bytes().decode("utf-8")
    return (text + _ACTIVITY_CODE_BLOCKS).encode("utf-8")


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-actvcode-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "actvcode-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def test_activity_codes_empty_before_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "actvcode-admin@example.com", "password": "secret123"})

    response = client.get(f"/projects/{project.id}/activity-codes")

    assert response.status_code == 200
    body = response.json()
    assert body["code_types"] == []
    assert body["code_values"] == []


def test_activity_codes_persisted_after_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "actvcode-admin@example.com", "password": "secret123"})

    upload = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("synthetic_project.xer", _fixture_with_activity_codes(), "application/octet-stream")},
    )
    assert upload.status_code == 201

    response = client.get(f"/projects/{project.id}/activity-codes")
    assert response.status_code == 200
    body = response.json()

    assert len(body["code_types"]) == 1
    assert body["code_types"][0]["actv_code_type_id"] == "CT1"
    assert body["code_types"][0]["name"] == "Phase"

    assert len(body["code_values"]) == 1
    value = body["code_values"][0]
    assert value["actv_code_id"] == "CV1"
    assert value["name"] == "Phase 1"
    assert value["short_name"] == "P1"
    assert value["code_type_id"] == body["code_types"][0]["id"]

    # TASKACTV assignments ship with the catalogue so Planning > Schedule can
    # show "<code> (~N activities)" and filter by code without a second call.
    activities = client.get(f"/activities?project_id={project.id}").json()
    a100 = next(a["id"] for a in activities if a["external_id"] == "A100")
    assert body["assignments"] == {value["id"]: [a100]}


def test_activity_codes_assignments_empty_without_taskactv(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "actvcode-admin@example.com", "password": "secret123"})

    upload = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("synthetic_project.xer", FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert upload.status_code == 201

    body = client.get(f"/projects/{project.id}/activity-codes").json()
    assert body["assignments"] == {}


def test_activity_codes_round_trip_through_export(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "actvcode-admin@example.com", "password": "secret123"})

    upload = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("synthetic_project.xer", _fixture_with_activity_codes(), "application/octet-stream")},
    )
    assert upload.status_code == 201

    response = client.get(f"/projects/{project.id}/export/xer")
    assert response.status_code == 200
    text = response.content.decode("utf-8")

    assert "CT1" in text
    assert "Phase 1" in text

    from app.parser.xer_parser import parse_xer

    reparsed = parse_xer(response.content)
    assert len(reparsed.code_types) == 1
    assert reparsed.code_types[0].actv_code_type_id == "CT1"
    assert len(reparsed.code_values) == 1
    assert len(reparsed.activity_codes) == 1
    # p6_task_id round-trips via Activity.p6_task_id ("1001"), captured at import time.
    assert reparsed.activity_codes[0].task_id == "1001"
