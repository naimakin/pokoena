"""Regression coverage for a production 500: `schedule_imports.data_date` is a
Postgres `timestamptz` column, so psycopg hands back a timezone-aware datetime on
read even though everything else in the schedule domain (parsed straight from the
.xer) is naive — comparing the two raises `TypeError: can't compare offset-naive
and offset-aware datetimes`. SQLite (what the rest of the suite runs against)
always returns naive values, so these tests force the aware case by hand to catch
what SQLite can't."""

import uuid
from datetime import datetime, timezone

from app.models.schedule_import import ScheduleImport
from app.services.schedule_current import to_naive
from tests.test_schedule_import import _setup, _upload


def test_to_naive_strips_tzinfo_and_leaves_naive_values_alone():
    aware = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
    assert to_naive(aware) == datetime(2026, 1, 5, 8, 0)
    assert to_naive(aware).tzinfo is None

    naive = datetime(2026, 1, 5, 8, 0)
    assert to_naive(naive) is naive
    assert to_naive(None) is None


def _make_current_import_timezone_aware(db_session, project_id) -> None:
    """Simulates what a real Postgres deployment hands back for the newest
    import's data_date — SQLite always returns it naive."""
    row = db_session.query(ScheduleImport).filter(ScheduleImport.project_id == project_id).one()
    row.data_date = row.data_date.replace(tzinfo=timezone.utc)
    db_session.commit()


def test_upload_does_not_crash_when_the_current_imports_data_date_is_aware(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    first = _upload(client, project.id).json()
    _make_current_import_timezone_aware(db_session, project.id)

    # synthetic_project.xer's data date is 2026-01-05 — force a clean newer upload
    # by bumping the stored (now aware) date backward, same shape as the real bug.
    row = db_session.query(ScheduleImport).filter(ScheduleImport.id == uuid.UUID(first["id"])).one()
    row.data_date = datetime(2025, 6, 1, tzinfo=timezone.utc)
    db_session.commit()

    response = _upload(client, project.id)

    assert response.status_code == 201


def test_regression_check_still_blocks_an_older_file_when_current_is_aware(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)
    _make_current_import_timezone_aware(db_session, project.id)

    from tests.test_schedule_import import OLDER_FIXTURE

    with open(OLDER_FIXTURE, "rb") as f:
        response = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("older_data_date.xer", f.read(), "application/octet-stream")},
        )

    assert response.status_code == 409


def test_edit_data_date_does_not_crash_when_the_stored_value_is_aware(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    imp = _upload(client, project.id).json()
    _make_current_import_timezone_aware(db_session, project.id)

    response = client.patch(
        f"/projects/{project.id}/schedule-imports/{imp['id']}", json={"data_date": "2026-02-10"}
    )

    assert response.status_code == 200
    assert response.json()["data_date"].startswith("2026-02-10")

    db_session.expire_all()
    stored = db_session.query(ScheduleImport).filter(ScheduleImport.id == uuid.UUID(imp["id"])).one()
    assert stored.data_date.tzinfo is None  # never writes an aware value back
