from app.models.user_tenant_role import TenantRole
from tests.factories import (
    add_membership,
    create_activity,
    create_project,
    create_schedule_import,
    create_tenant,
    create_user,
)


def _snap(external_id, finish, **kw):
    return {
        "external_id": external_id,
        "p6_task_id": kw.get("p6_task_id"),
        "name": kw.get("name", external_id),
        "wbs_path": kw.get("wbs_path"),
        "planned_finish": finish,
        "early_finish": None,
        "actual_finish": None,
        "is_critical": kw.get("is_critical", False),
        "is_longest_path": False,
        "total_float_hours": kw.get("total_float_hours"),
        "status": "in_progress",
        "percent_complete": 20,
    }


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-slips")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "slips-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, admin


def _login(client):
    client.post("/auth/login", json={"email": "slips-admin@example.com", "password": "secret123"})


def test_empty_when_no_snapshots(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    body = client.get(f"/projects/{project.id}/recovery-plan").json()
    assert body["comparison_basis"] == "none"
    assert body["slipped"] == []


def test_slips_between_two_updates(client, db_session):
    tenant, project, admin = _setup(db_session)
    create_activity(db_session, tenant, project, "A100")
    create_activity(db_session, tenant, project, "A200")
    create_schedule_import(
        db_session, tenant, project, admin, revision_no=1, revision_label="UPD-1",
        snapshot=[_snap("A100", "2026-06-01"), _snap("A200", "2026-06-01", is_critical=True)],
    )
    create_schedule_import(
        db_session, tenant, project, admin, revision_no=2, revision_label="UPD-2",
        snapshot=[_snap("A100", "2026-06-20"), _snap("A200", "2026-06-03", is_critical=True)],
    )
    _login(client)

    body = client.get(f"/projects/{project.id}/recovery-plan").json()
    assert body["comparison_basis"] == "previous_upd"
    assert body["from_import"]["revision_label"] == "UPD-1"
    assert body["to_import"]["revision_label"] == "UPD-2"
    ids = {r["external_id"]: r for r in body["slipped"]}
    assert ids["A100"]["slip_days"] == 19 and ids["A100"]["plan_required"] is True  # >= 5d
    assert ids["A200"]["slip_days"] == 2 and ids["A200"]["plan_required"] is True   # critical bypass
    assert body["summary"]["plans_required"] == 2
    assert body["summary"]["plans_submitted"] == 0


def test_threshold_param_hides_small_non_critical_slip(client, db_session):
    tenant, project, admin = _setup(db_session)
    create_activity(db_session, tenant, project, "A100")
    create_schedule_import(db_session, tenant, project, admin, revision_no=1, revision_label="UPD-1",
                           snapshot=[_snap("A100", "2026-06-01")])
    create_schedule_import(db_session, tenant, project, admin, revision_no=2, revision_label="UPD-2",
                           snapshot=[_snap("A100", "2026-06-04")])
    _login(client)

    assert client.get(f"/projects/{project.id}/recovery-plan?threshold_days=1").json()["slipped"][0]["slip_days"] == 3
    assert client.get(f"/projects/{project.id}/recovery-plan?threshold_days=5").json()["slipped"] == []


def test_baseline_fallback_on_upd1(client, db_session):
    tenant, project, admin = _setup(db_session)
    create_activity(db_session, tenant, project, "A100")
    create_schedule_import(db_session, tenant, project, admin, revision_no=None, revision_label="Baseline programme",
                           snapshot=[_snap("A100", "2026-06-01")])
    create_schedule_import(db_session, tenant, project, admin, revision_no=1, revision_label="UPD-1",
                           snapshot=[_snap("A100", "2026-06-15")])
    _login(client)

    body = client.get(f"/projects/{project.id}/recovery-plan").json()
    assert body["comparison_basis"] == "baseline_programme"
    assert body["slipped"][0]["slip_days"] == 14
