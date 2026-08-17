import io
from pathlib import Path

import openpyxl

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-evm-export-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "evm-export-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def test_export_requires_active_baseline(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "evm-export-admin@example.com", "password": "secret123"})
    with open(FIXTURE, "rb") as f:
        client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )

    response = client.get(f"/projects/{project.id}/evm/export")

    assert response.status_code == 423


def test_export_returns_valid_workbook_with_expected_sheets(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "evm-export-admin@example.com", "password": "secret123"})
    with open(FIXTURE, "rb") as f:
        client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    client.post(f"/projects/{project.id}/evm/baseline", json={"version_label": "Target-1"})

    response = client.get(f"/projects/{project.id}/evm/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "Content-Disposition" in response.headers

    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    assert wb.sheetnames == ["Executive Dashboard", "Baseline Activities"]

    activities_sheet = wb["Baseline Activities"]
    header_row = [cell.value for cell in activities_sheet[1]][1:7]
    assert header_row == ["Activity Code", "Activity Name", "WBS", "Planned MH", "Baseline Start", "Baseline End"]
