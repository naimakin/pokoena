"""Hours → days on each activity's OWN calendar (engine/durations.py).

P6 shows TASK.total_float_hr_cnt / target_drtn_hr_cnt in days by dividing by
the activity's calendar's CALENDAR.day_hr_cnt — never a flat 8, and never one
project-wide divisor when activities sit on different calendars."""

from pathlib import Path

import pytest

from app.models.user_tenant_role import TenantRole
from app.parser.xer_parser import parse_xer
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"

_CAL_HEADER = "%F\tclndr_id\tclndr_name\tproj_id\tclndr_data"
_CAL1_ROW = "%R\tCAL1\tStandard 5 Day\t\t(0)(1|08:00|17:00)(2|08:00|17:00)(3|08:00|17:00)(4|08:00|17:00)(5|08:00|17:00)(6)"
_TEN_HOUR_WEEK = "(0)(1|07:00|17:00)(2|07:00|17:00)(3|07:00|17:00)(4|07:00|17:00)(5|07:00|17:00)(6)"


def _two_calendar_xer() -> bytes:
    """The synthetic fixture with day_hr_cnt declared (CAL1 at 8h even though
    its shift spans 9h — i.e. a lunch hour P6 knows about) and a second, 10h
    calendar that A400/A500 run on."""
    text = FIXTURE.read_bytes().decode("utf-8")
    assert _CAL_HEADER in text and _CAL1_ROW in text
    text = text.replace(_CAL_HEADER, "%F\tclndr_id\tclndr_name\tproj_id\tday_hr_cnt\tclndr_data")
    text = text.replace(
        _CAL1_ROW,
        "%R\tCAL1\tStandard 5 Day\t\t8\t(0)(1|08:00|17:00)(2|08:00|17:00)(3|08:00|17:00)(4|08:00|17:00)(5|08:00|17:00)(6)"
        f"\r\n%R\tCAL2\tTen Hour Day\t\t10\t{_TEN_HOUR_WEEK}",
    )
    for code in ("A400", "A500"):
        text = text.replace(f"\tCAL1\t{code}\t", f"\tCAL2\t{code}\t")
    return text.encode("utf-8")


def test_parser_reads_day_hr_cnt_over_the_shift_average():
    parsed = parse_xer(_two_calendar_xer())
    by_id = {c.clndr_id: c for c in parsed.calendars}
    assert by_id["CAL1"].hours_per_day == 8.0  # shifts alone would say 9
    assert by_id["CAL2"].hours_per_day == 10.0


def test_parser_falls_back_to_the_shift_average_without_day_hr_cnt():
    parsed = parse_xer(FIXTURE.read_bytes())
    assert parsed.calendars[0].hours_per_day == pytest.approx(9.0)


def _import(client, db_session, slug):
    tenant = create_tenant(db_session, name="Acme", slug=slug)
    project = create_project(db_session, tenant)
    user = create_user(db_session, f"{slug}@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": f"{slug}@example.com", "password": "secret123"})
    upload = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("two_calendars.xer", _two_calendar_xer(), "application/octet-stream")},
    )
    assert upload.status_code == 201
    return project, upload.json()


def test_each_activity_carries_its_own_calendar_day_length(client, db_session):
    project, _ = _import(client, db_session, "cal-hpd-1")

    rows = {a["external_id"]: a for a in client.get(f"/activities?project_id={project.id}").json()}

    assert rows["A100"]["hours_per_day"] == 8.0
    assert rows["A400"]["hours_per_day"] == 10.0
    assert rows["A500"]["hours_per_day"] == 10.0
    # remaining_duration_days is read on the same calendar: A500 is 16h.
    assert rows["A500"]["remaining_duration_days"] == round(16 / 10)
    assert rows["A200"]["remaining_duration_days"] == 40 // 8


def test_float_is_shown_in_the_activitys_own_calendar_days(client, db_session):
    project, _ = _import(client, db_session, "cal-hpd-2")
    rows = {a["external_id"]: a for a in client.get(f"/activities?project_id={project.id}").json()}
    assert rows["A400"]["total_float_hours"]  # the side chain has float to read

    candidates = {
        c["external_id"]: c for c in client.get(f"/projects/{project.id}/float-path/end-candidates").json()
    }
    for code in ("A100", "A400", "A500"):
        tf_hours = rows[code]["total_float_hours"]
        expected = round(tf_hours / rows[code]["hours_per_day"], 2)
        assert candidates[code]["total_float_days"] == expected


def test_an_earlier_programme_view_keeps_the_calendar_it_was_imported_with(client, db_session):
    project, upload = _import(client, db_session, "cal-hpd-3")

    rows = client.get(f"/projects/{project.id}/schedule-imports/{upload['id']}/activities").json()
    by_code = {a["external_id"]: a for a in rows}

    assert by_code["A100"]["hours_per_day"] == 8.0
    assert by_code["A400"]["hours_per_day"] == 10.0
