"""The % Poko shows, and what a % entered in Poko writes
(services/activity_progress.py):

- labor resources assigned (TASKRSRC, RT_Labor): % = act_reg_qty / target_qty,
  and an entered % splits their units;
- none: Completed 100, Not Started 0, In Progress the duration %
  (target_drtn - remain_drtn) / target_drtn; an entered % is stored as the
  physical % and moves the remaining duration so the two agree.
"""

from app.engine.export.xer_progress import decode_xer
from app.models.activity import ActivityStatus
from app.services.activity_progress import display_percent
from tests.test_progress_roundtrip import (
    RESOURCE_LOADED,
    SYNTHETIC,
    _activity,
    _assignments,
    _edit_rows,
    _login,
    _table,
    _upload,
)
from tests.test_schedule_import import _setup


def test_display_percent_rules():
    # Labor units win whatever the status.
    assert display_percent(ActivityStatus.in_progress, 40, 30, labor_budget=40, labor_actual=30) == 75
    assert display_percent(ActivityStatus.complete, 40, 0) == 100
    assert display_percent(ActivityStatus.not_started, 40, 40, phys_pct=30) == 0
    # In progress without labor: duration %, not the physical %.
    assert display_percent(ActivityStatus.in_progress, 40, 30, phys_pct=80) == 25
    # ... unless there is no duration to go by.
    assert display_percent(ActivityStatus.in_progress, 0, 0, phys_pct=40) == 40
    assert display_percent(ActivityStatus.in_progress, None, None) == 0


def test_import_shows_duration_percent_for_an_activity_without_resources(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    text = _edit_rows(
        SYNTHETIC.read_text("utf-8"),
        "TASK",
        {"task_code": "A200"},  # 40h, no resources
        {
            "status_code": "TK_Active",
            "phys_complete_pct": "80",
            "remain_drtn_hr_cnt": "30",
            "act_start_date": "2026-01-06 08:00",
        },
    )
    _upload(client, project.id, text.encode("utf-8"))

    a200 = _activity(db_session, project.id, "A200")
    assert a200.status == ActivityStatus.in_progress
    assert a200.percent_complete == 25
    assert a200.phys_complete_pct == 80


def test_import_shows_labor_units_percent_for_a_resourced_activity(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    text = _edit_rows(
        RESOURCE_LOADED.read_text("utf-8"),
        "TASK",
        {"task_code": "A200"},
        {"status_code": "TK_Active", "phys_complete_pct": "5", "act_start_date": "2026-01-06 08:00"},
    )
    # A200: R1 (labor, 40h budget) + R3 (material, 100) — material doesn't count.
    text = _edit_rows(text, "TASKRSRC", {"taskrsrc_id": "2"}, {"act_reg_qty": "10", "remain_qty": "30"})
    text = _edit_rows(text, "TASKRSRC", {"taskrsrc_id": "3"}, {"act_reg_qty": "90", "remain_qty": "10"})
    _upload(client, project.id, text.encode("utf-8"))

    assert _activity(db_session, project.id, "A200").percent_complete == 25


def test_percent_entry_without_resources_sets_physical_pct_and_remaining(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, SYNTHETIC.read_bytes())
    a300 = _activity(db_session, project.id, "A300")  # 24h on a 9h/day calendar (08:00-17:00)

    body = client.patch(
        f"/activities/{a300.id}", json={"actual_start": "2026-01-12", "percent_complete": 50}
    ).json()

    assert body["status"] == "in_progress"
    assert body["percent_complete"] == 50
    assert body["phys_complete_pct"] == 50
    assert body["remaining_duration_hours"] == 12
    assert body["remaining_duration_days"] == 1  # 12h / 9h

    exported = client.get(f"/projects/{project.id}/export/xer")
    text, _ = decode_xer(exported.content)
    task = next(r for r in _table(text, "TASK") if r["task_code"] == "A300")
    assert task["phys_complete_pct"] == "50"
    assert task["remain_drtn_hr_cnt"] == "12"


def test_remaining_duration_entry_moves_the_duration_percent(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, SYNTHETIC.read_bytes())
    a300 = _activity(db_session, project.id, "A300")
    client.patch(f"/activities/{a300.id}", json={"actual_start": "2026-01-12"})

    body = client.patch(f"/activities/{a300.id}", json={"remaining_duration_days": 2}).json()

    assert body["remaining_duration_hours"] == 18
    assert body["percent_complete"] == 25  # (24 - 18) / 24


def test_unchanged_percent_riding_along_is_not_an_entry(client, db_session):
    """The Activity modal sends every field on save; a % that didn't move must
    not be taken as a % entry (it would reset the remaining duration)."""
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, SYNTHETIC.read_bytes())
    a300 = _activity(db_session, project.id, "A300")
    client.patch(f"/activities/{a300.id}", json={"actual_start": "2026-01-12", "percent_complete": 50})

    body = client.patch(
        f"/activities/{a300.id}", json={"percent_complete": 50, "remaining_duration_days": 2, "notes": "x"}
    ).json()

    assert body["remaining_duration_hours"] == 18
    assert body["percent_complete"] == 25


def test_percent_entry_with_labor_resources_splits_labor_units_only(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, RESOURCE_LOADED.read_bytes())
    a200 = _activity(db_session, project.id, "A200")

    body = client.patch(f"/activities/{a200.id}", json={"percent_complete": 40}).json()

    assert body["percent_complete"] == 40
    by_budget = _assignments(db_session, a200.id)
    assert (by_budget[40].act_reg_qty, by_budget[40].remain_qty) == (16, 24)
    assert by_budget[100].act_reg_qty == 0  # RT_Material
