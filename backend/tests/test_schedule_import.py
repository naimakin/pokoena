import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.activity import Activity
from app.models.schedule_import import ScheduleImport
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"
COMPLETED_FIXTURE = Path(__file__).parent / "fixtures" / "completed_not_critical.xer"
OLDER_FIXTURE = Path(__file__).parent / "fixtures" / "older_data_date.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-xer-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "xer-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _set_imported_at(db_session, import_id: str, dt: datetime) -> None:
    # SQLite's CURRENT_TIMESTAMP (unlike Postgres's now() in production) only
    # has second resolution, so back-to-back uploads in a test can tie on
    # imported_at — force a deterministic order for "which one is latest".
    row = db_session.query(ScheduleImport).filter(ScheduleImport.id == uuid.UUID(import_id)).one()
    row.imported_at = dt
    db_session.commit()


def _upload(client, project_id):
    with open(FIXTURE, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )


def test_upload_schedules_activities_and_returns_summary(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    response = _upload(client, project.id)

    assert response.status_code == 201
    body = response.json()
    assert body["activity_count"] == 6
    assert body["critical_count"] == 4
    assert body["filename"] == "synthetic_project.xer"


def test_activities_reflect_cpm_results_after_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    response = client.get(f"/activities?project_id={project.id}")
    assert response.status_code == 200
    by_code = {a["external_id"]: a for a in response.json()}

    assert set(by_code) == {"A100", "A200", "A300", "A400", "A500", "A600"}
    assert by_code["A300"]["is_critical"] is True
    assert by_code["A300"]["total_float_hours"] == 0
    assert by_code["A500"]["is_critical"] is False
    assert by_code["A500"]["total_float_hours"] == 40
    assert by_code["A200"]["early_start"] == "2026-01-05"
    assert by_code["A100"]["status"] == "not_started"
    assert by_code["A100"]["remaining_duration_days"] == 1


def test_completed_activity_is_not_critical_even_at_zero_float(client, db_session):
    # The CPM scheduler force-sets total_float_hr_cnt=0.0 for every TK_Complete
    # task (app/engine/cpm/scheduler.py) regardless of actual slack — that's a
    # display convention, not a signal that finished work is still "critical".
    # A finished activity with no remaining work should never show as critical,
    # even though its raw total float reads 0, same as a genuinely critical one.
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    with open(COMPLETED_FIXTURE, "rb") as f:
        response = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("completed_not_critical.xer", f.read(), "application/octet-stream")},
        )
    assert response.status_code == 201
    assert response.json()["critical_count"] == 1  # only the not-yet-started successor

    by_code = {a["external_id"]: a for a in client.get(f"/activities?project_id={project.id}").json()}
    assert by_code["C100"]["total_float_hours"] == 0  # scheduler's display convention
    assert by_code["C100"]["is_critical"] is False  # but it's finished, so not critical
    assert by_code["C200"]["is_critical"] is True  # genuinely on the critical path


def test_is_critical_rule():
    from app.services.xer_import import _is_critical

    end = datetime(2026, 1, 5)
    assert _is_critical(0.0, "TK_Active", None) is True
    assert _is_critical(-16.0, "TK_NotStart", None) is True
    assert _is_critical(8.0, "TK_Active", None) is False
    assert _is_critical(None, "TK_NotStart", None) is False  # empty float is never critical
    # An actual finish (or TK_Complete) rules criticality out whatever the float says.
    assert _is_critical(0.0, "TK_Active", end) is False
    assert _is_critical(-16.0, "TK_NotStart", end) is False
    assert _is_critical(0.0, "TK_Complete", None) is False


def test_reimport_preserves_subcontractor_owned_progress_fields(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    a100 = db_session.query(Activity).filter(Activity.project_id == project.id, Activity.external_id == "A100").one()
    patch_resp = client.patch(f"/activities/{a100.id}", json={"percent_complete": 40})
    assert patch_resp.status_code == 200

    _upload(client, project.id)

    db_session.expire_all()
    refreshed = db_session.query(Activity).filter(Activity.id == a100.id).one()
    assert refreshed.percent_complete == 40
    # P6-native fields still get overwritten by the re-import.
    assert refreshed.total_float_hours == 0


def test_import_preserves_user_entered_actuals_including_rename(client, db_session):
    """A company user enters actual dates on the Progress page, then a planner
    re-imports the .xer — even one where the activity's P6 Activity ID changed.
    The user's actuals + derived status must survive (matched by p6_task_id)."""
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    a100 = db_session.query(Activity).filter(
        Activity.project_id == project.id, Activity.external_id == "A100"
    ).one()
    patch = client.patch(
        f"/activities/{a100.id}",
        json={"actual_start": "2026-01-05", "actual_finish": "2026-01-06"},
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "complete"

    # Re-import with A100 renamed to A100X (task_id 1001 unchanged).
    renamed = FIXTURE.read_bytes().decode("utf-8").replace("\tA100\t", "\tA100X\t")
    resp = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("renamed.xer", renamed.encode("utf-8"), "application/octet-stream")},
    )
    assert resp.status_code == 201

    db_session.expire_all()
    same_row = db_session.query(Activity).filter(Activity.id == a100.id).one()
    assert same_row.external_id == "A100X"
    assert same_row.actual_start is not None
    assert same_row.actual_finish is not None
    assert same_row.status.value == "complete"
    assert same_row.percent_complete == 100
    # No orphaned duplicate left behind.
    assert db_session.query(Activity).filter(
        Activity.project_id == project.id, Activity.external_id == "A100"
    ).count() == 0


def test_import_relinks_recovery_plan_on_rename(client, db_session):
    import uuid as _uuid

    from app.models.recovery_plan import RecoveryPlan
    from tests.factories import create_user

    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    author = create_user(db_session, "rp-relink@example.com", "secret123")
    plan = RecoveryPlan(
        id=_uuid.uuid4(), tenant_id=tenant.id, project_id=project.id,
        activity_external_id="A100", activity_name="Mobilization",
        created_by_user_id=author.id,
    )
    db_session.add(plan)
    db_session.commit()

    renamed = FIXTURE.read_bytes().decode("utf-8").replace("\tA100\t", "\tA100X\t")
    resp = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("renamed.xer", renamed.encode("utf-8"), "application/octet-stream")},
    )
    assert resp.status_code == 201
    db_session.expire_all()
    assert db_session.query(RecoveryPlan).filter(RecoveryPlan.id == plan.id).one().activity_external_id == "A100X"


def test_import_writes_activities_snapshot(client, db_session):
    from app.models.schedule_import import ScheduleImport

    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    imp = db_session.query(ScheduleImport).filter(ScheduleImport.project_id == project.id).one()
    snap = imp.activities_snapshot
    assert len(snap) == 6
    row = next(a for a in snap if a["external_id"] == "A300")
    assert set(row) >= {
        "external_id", "planned_start", "planned_finish", "target_duration_hours",
        "constraint_type", "task_type", "is_critical", "status", "percent_complete",
    }
    assert row["is_critical"] is True


def test_first_import_auto_locks_baseline(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    assert _upload(client, project.id).status_code == 201

    status = client.get(f"/projects/{project.id}/evm/baseline").json()
    assert status["has_active"] is True
    assert status["active_baseline"]["version_label"] == "Baseline"


def test_second_import_does_not_relock_baseline(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    assert _upload(client, project.id).status_code == 201
    first_baseline = client.get(f"/projects/{project.id}/evm/baseline").json()["active_baseline"]

    assert _upload(client, project.id).status_code == 201
    status = client.get(f"/projects/{project.id}/evm/baseline").json()

    assert len(status["all_baselines"]) == 1
    assert status["active_baseline"]["id"] == first_baseline["id"]


def test_history_endpoint_lists_past_imports(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    response = client.get(f"/projects/{project.id}/schedule-imports")
    assert response.status_code == 200
    imports = response.json()
    assert len(imports) == 1
    assert imports[0]["activity_count"] == 6


def test_rejects_non_xer_file(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    response = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("not-an-xer.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_import_rejects_a_cyclic_relationship_network(client, db_session):
    """A real P6 export with a circular dependency (CPM can't be run on it)
    must come back as a clear 400, not an unhandled 500 — this is the first
    real-world .xer this app ever imported to surface CpmCycleError going
    uncaught (see app/main.py's global exception handler for the other half
    of this fix)."""
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    text = FIXTURE.read_bytes().decode("utf-8")
    # A600 (1006) already depends on A300 (1003) and A500 (1005); adding
    # A100 (1001) -> depends on -> A600 closes the loop 1001->1002->1003->1006->1001.
    cyclic_bytes = (text + "%R\t7\t1001\tPROJ1\t1006\tPROJ1\tPR_FS\t0\n").encode("utf-8")

    response = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("cyclic.xer", cyclic_bytes, "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "circular dependency" in response.json()["detail"].lower()
    # Nothing partially written — schedule() raises before any DB writes happen.
    assert client.get(f"/projects/{project.id}/schedule-imports").json() == []


def test_import_rejects_a_calendar_with_no_working_days(client, db_session):
    """A real production import crashed with an unhandled RuntimeError from
    CalendarEngine.snap_to_work_start when a project's calendar had no
    working day at all (an empty/placeholder week — plausible in a real P6
    "template" export). Must come back as a clear 400 instead."""
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    text = FIXTURE.read_bytes().decode("utf-8")
    blank_calendar_text = text.replace(
        "(0)(1|08:00|17:00)(2|08:00|17:00)(3|08:00|17:00)(4|08:00|17:00)(5|08:00|17:00)(6)",
        "(0)(1)(2)(3)(4)(5)(6)",
    )
    assert blank_calendar_text != text  # the replace actually matched something

    response = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("blank-calendar.xer", blank_calendar_text.encode("utf-8"), "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "no working day" in response.json()["detail"].lower()


def test_unexpected_import_error_returns_a_proper_500_with_cors_headers(client, db_session, monkeypatch):
    """Regression test for a real production symptom: an unhandled exception
    reaching the browser with no CORS headers at all, which shows up as a
    misleading "blocked by CORS policy" error instead of the real 500 — see
    app/main.py's catch_unhandled_exceptions middleware and the comment on
    why it has to be a plain middleware (added before CORSMiddleware), not an
    @app.exception_handler(Exception)."""
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    def _boom(*args, **kwargs):
        raise RuntimeError("something truly unexpected")

    monkeypatch.setattr("app.api.routes.schedule_imports.import_xer", _boom)

    with open(FIXTURE, "rb") as f:
        response = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_delete_schedule_import_blocks_the_current_one(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    latest = _upload(client, project.id).json()

    response = client.delete(f"/projects/{project.id}/schedule-imports/{latest['id']}")

    assert response.status_code == 409
    assert "current schedule" in response.json()["detail"]


def test_delete_schedule_import_blocks_a_baseline_linked_one(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    base = datetime.now(timezone.utc)
    first = _upload(client, project.id).json()  # auto-locked as the baseline
    _set_imported_at(db_session, first["id"], base)
    second = _upload(client, project.id).json()  # now the current one
    _set_imported_at(db_session, second["id"], base + timedelta(minutes=1))

    response = client.delete(f"/projects/{project.id}/schedule-imports/{first['id']}")

    assert response.status_code == 409
    assert "baseline" in response.json()["detail"]


def test_delete_schedule_import_removes_a_superseded_one(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    base = datetime.now(timezone.utc)
    first = _upload(client, project.id).json()  # #1, auto-locked as the baseline
    _set_imported_at(db_session, first["id"], base)
    middle = _upload(client, project.id).json()  # #2, deletable
    _set_imported_at(db_session, middle["id"], base + timedelta(minutes=1))
    last = _upload(client, project.id).json()  # #3, the current one
    _set_imported_at(db_session, last["id"], base + timedelta(minutes=2))

    response = client.delete(f"/projects/{project.id}/schedule-imports/{middle['id']}")

    assert response.status_code == 204
    remaining_ids = {i["id"] for i in client.get(f"/projects/{project.id}/schedule-imports").json()}
    assert middle["id"] not in remaining_ids
    assert len(remaining_ids) == 2


def test_rename_schedule_import_updates_the_revision_label(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    imp = _upload(client, project.id).json()

    response = client.patch(
        f"/projects/{project.id}/schedule-imports/{imp['id']}", json={"revision_label": "  Mar close-out  "}
    )

    assert response.status_code == 200
    assert response.json()["revision_label"] == "Mar close-out"
    listed = client.get(f"/projects/{project.id}/schedule-imports").json()
    assert listed[0]["revision_label"] == "Mar close-out"
    # Filename / data date are file-derived and untouched.
    assert listed[0]["filename"] == imp["filename"]
    assert listed[0]["data_date"] == imp["data_date"]


def test_rename_schedule_import_rejects_a_blank_or_overlong_label(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    imp = _upload(client, project.id).json()
    url = f"/projects/{project.id}/schedule-imports/{imp['id']}"

    assert client.patch(url, json={"revision_label": ""}).status_code == 422
    assert client.patch(url, json={"revision_label": "   "}).status_code == 400
    assert client.patch(url, json={"revision_label": "x" * 31}).status_code == 422


def test_upload_blocks_a_data_date_regression(client, db_session):
    # synthetic_project.xer's data date (2026-01-05) is newer than
    # older_data_date.xer's (2025-06-01) — uploading the older file next would
    # silently move the live schedule backward, so it must be blocked by
    # default.
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    with open(OLDER_FIXTURE, "rb") as f:
        response = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("older_data_date.xer", f.read(), "application/octet-stream")},
        )

    assert response.status_code == 409
    assert "data date" in response.json()["detail"]

    # The live schedule must be untouched — still the original 6 activities.
    assert len(client.get(f"/activities?project_id={project.id}").json()) == 6


def test_upload_data_date_regression_can_be_forced(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    with open(OLDER_FIXTURE, "rb") as f:
        response = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("older_data_date.xer", f.read(), "application/octet-stream")},
            data={"force": "true"},
        )

    assert response.status_code == 201
    assert response.json()["activity_count"] == 1
