from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-dcma-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "dcma-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def test_dcma_report_requires_import_free_schedule_still_returns(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "dcma-admin@example.com", "password": "secret123"})

    response = client.get(f"/projects/{project.id}/dcma")

    assert response.status_code == 200
    body = response.json()
    assert body["total_activities"] == 0
    assert len(body["checks"]) == 15
    oos = next(c for c in body["checks"] if c["id"] == 15)
    assert oos["scored"] is False
    assert oos["basis"] == "relationships"


def test_dcma_report_after_schedule_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "dcma-admin@example.com", "password": "secret123"})

    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert upload.status_code == 201

    response = client.get(f"/projects/{project.id}/dcma")
    assert response.status_code == 200
    body = response.json()

    assert body["total_activities"] == 6
    by_id = {c["id"]: c for c in body["checks"]}
    # The synthetic fixture has no RSRC/TASKRSRC data, so every non-milestone
    # in-scope activity is "unassigned" — check #10 is real now (Slice 6), not
    # not_tracked, since the route always loads (possibly empty) assignment
    # data. A600 (finish milestone) is excluded from the numerator (same
    # milestone exclusion as check #1) but still counts in the denominator:
    # 5 of 6 unassigned.
    assert by_id[10]["status"] == "warn"
    assert by_id[10]["pct"] == 83.33
    # A100 (Mobilization) has no predecessor and isn't a milestone, so it's a
    # genuine open end at the start of the network — A600 (finish milestone)
    # is excluded from the check by task type despite having no successor.
    assert by_id[1]["status"] == "fail"
    assert by_id[1]["details"] == ["A100"]
    # A400/A500 carry 40h of float — well under the 44-working-day (352h)
    # high-float threshold.
    assert by_id[6]["status"] == "pass"
    assert body["overall_score"] > 0


# --- a project's own targets ------------------------------------------------


def _import(client, project):
    with open(FIXTURE, "rb") as f:
        r = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert r.status_code == 201


def test_project_targets_change_the_verdicts(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "dcma-admin@example.com", "password": "secret123"})
    _import(client, project)

    before = client.get(f"/projects/{project.id}/dcma").json()
    assert before["customized"] == [] and before["can_edit_thresholds"] is True
    assert before["thresholds"]["logic_max"] == 5.0 == before["default_thresholds"]["logic_max"]
    by_id = {c["id"]: c for c in before["checks"]}
    assert by_id[1]["status"] == "fail" and by_id[6]["value"] == 0

    saved = client.put(
        f"/projects/{project.id}/dcma/thresholds",
        json={"logic_max": 20, "resources_max": 90, "high_float_days": 4, "lags_max": 5},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["customized"] == ["high_float_days", "logic_max", "resources_max"]  # 5 is DCMA's own

    after = client.get(f"/projects/{project.id}/dcma").json()
    by_id = {c["id"]: c for c in after["checks"]}
    assert by_id[1]["status"] == "pass" and by_id[1]["threshold"] == 20
    assert by_id[10]["status"] == "pass"
    # A400/A500 carry 4.44 days of float: over a 4-day "high float" bar.
    assert by_id[6]["value"] == 2 and by_id[6]["name"] == "High Float (TF > 4d)"
    assert after["overall_score"] > before["overall_score"]

    # Back to DCMA's own.
    assert client.put(f"/projects/{project.id}/dcma/thresholds", json={}).status_code == 200
    reset = client.get(f"/projects/{project.id}/dcma").json()
    assert reset["customized"] == [] and reset["overall_score"] == before["overall_score"]


def test_targets_are_validated_and_need_edit_rights(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "dcma-admin@example.com", "password": "secret123"})

    bad = client.put(f"/projects/{project.id}/dcma/thresholds", json={"logic_max": 120, "cp_length_min": 30})
    assert bad.status_code == 422
    assert set(bad.json()["detail"]["errors"]) == {"logic_max", "cp_length_min"}

    viewer = create_user(db_session, "dcma-viewer@example.com", "secret123")
    add_membership(db_session, viewer, tenant, TenantRole.company_employee)
    import uuid

    from app.models.project_membership import ProjectMembership

    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=viewer.id))
    db_session.commit()
    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "dcma-viewer@example.com", "password": "secret123"})
    assert client.get(f"/projects/{project.id}/dcma").json()["can_edit_thresholds"] is False
    assert client.put(f"/projects/{project.id}/dcma/thresholds", json={"logic_max": 10}).status_code == 403
