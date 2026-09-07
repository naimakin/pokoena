from app.models.user_tenant_role import TenantRole
from tests.factories import (
    add_membership,
    create_project,
    create_schedule_import,
    create_tenant,
    create_user,
)


def _a(external_id, finish, **kw):
    return {
        "external_id": external_id, "p6_task_id": kw.get("p6_task_id"), "name": external_id,
        "wbs_path": kw.get("wbs_path", "W1"), "task_type": "TT_Task",
        "planned_start": kw.get("start"), "planned_finish": finish,
        "early_start": None, "early_finish": None, "actual_start": None, "actual_finish": None,
        "target_duration_hours": kw.get("dur"), "remaining_duration_hours": None,
        "constraint_type": None, "constraint_date": None,
        "is_critical": kw.get("is_critical", False), "is_longest_path": False,
        "total_float_hours": None, "status": "in_progress", "percent_complete": 20,
    }


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-changes")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "chg-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, admin


def _login(client, email="chg-admin@example.com"):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def test_empty_before_two_imports(client, db_session):
    tenant, project, _ = _setup(db_session)
    _login(client)
    body = client.get(f"/projects/{project.id}/schedule-changes").json()
    assert body["comparison_basis"] == "none"
    assert body["summary"]["activities_modified"] == 0


def test_full_diff_between_two_updates(client, db_session):
    tenant, project, admin = _setup(db_session)
    create_schedule_import(
        db_session, tenant, project, admin, revision_no=1, revision_label="UPD-1",
        snapshot=[_a("A100", "2026-06-01", dur=80), _a("GONE", "2026-06-01")],
    )
    create_schedule_import(
        db_session, tenant, project, admin, revision_no=2, revision_label="UPD-2",
        snapshot=[_a("A100", "2026-06-20", dur=120), _a("NEW", "2026-07-01")],
    )
    _login(client)

    body = client.get(f"/projects/{project.id}/schedule-changes").json()
    assert body["comparison_basis"] == "previous_upd"
    assert body["from_import"]["revision_label"] == "UPD-1"
    assert body["summary"]["activities_added"] == 1
    assert body["summary"]["activities_removed"] == 1
    mod = body["activities"]["modified"][0]
    assert mod["external_id"] == "A100"
    fields = {f["field"] for f in mod["fields"]}
    assert "finish" in fields and "duration" in fields


def test_explicit_import_override_and_thresholds(client, db_session):
    tenant, project, admin = _setup(db_session)
    i1 = create_schedule_import(db_session, tenant, project, admin, revision_no=1, revision_label="UPD-1",
                                snapshot=[_a("A100", "2026-06-01")])
    i2 = create_schedule_import(db_session, tenant, project, admin, revision_no=2, revision_label="UPD-2",
                                snapshot=[_a("A100", "2026-06-03")])
    _login(client)

    b1 = client.get(
        f"/projects/{project.id}/schedule-changes",
        params={"from_import_id": str(i1.id), "to_import_id": str(i2.id), "date_threshold_days": 1},
    ).json()
    assert b1["summary"]["activities_modified"] == 1
    b2 = client.get(
        f"/projects/{project.id}/schedule-changes",
        params={"from_import_id": str(i1.id), "to_import_id": str(i2.id), "date_threshold_days": 5},
    ).json()
    assert b2["summary"]["activities_modified"] == 0


def test_unknown_import_400(client, db_session):
    import uuid

    tenant, project, _ = _setup(db_session)
    _login(client)
    r = client.get(f"/projects/{project.id}/schedule-changes", params={"from_import_id": str(uuid.uuid4())})
    assert r.status_code == 400


def test_falls_back_to_frozen_baseline_when_prev_has_no_snapshot(client, db_session):
    """Pre-feature projects: the older import carries no activities_snapshot, so
    the diff compares against the frozen baseline_activities instead."""
    from pathlib import Path

    from app.models.schedule_import import ScheduleImport

    fixture = Path(__file__).parent / "fixtures" / "synthetic_project.xer"
    tenant, project, admin = _setup(db_session)
    client.post("/auth/login", json={"email": "chg-admin@example.com", "password": "secret123"})

    def _upload():
        with open(fixture, "rb") as f:
            return client.post(
                f"/projects/{project.id}/schedule-imports",
                files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
            )

    assert _upload().status_code == 201  # first import → auto-locks baseline
    # simulate that the baseline import predates the snapshot column
    baseline_import = (
        db_session.query(ScheduleImport)
        .filter(ScheduleImport.project_id == project.id)
        .order_by(ScheduleImport.imported_at)
        .first()
    )
    baseline_import.activities_snapshot = []
    db_session.commit()

    assert _upload().status_code == 201  # UPD-1, has a snapshot

    body = client.get(f"/projects/{project.id}/schedule-changes").json()
    assert body["comparison_basis"] == "baseline_frozen"
    assert body["coverage"] == {"from_snapshot": True, "to_snapshot": True}


def test_cross_tenant_project_404(client, db_session):
    tenant, project, _ = _setup(db_session)
    other = create_tenant(db_session, name="Other", slug="other-changes")
    other_project = create_project(db_session, other)
    _login(client)
    assert client.get(f"/projects/{other_project.id}/schedule-changes").status_code in (403, 404)
