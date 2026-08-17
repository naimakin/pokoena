from pathlib import Path

import pytest

from app.parser.xer_parser import XerParseError, parse_xer

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _load() -> bytes:
    return FIXTURE.read_bytes()


def test_parses_project_meta():
    parsed = parse_xer(_load())
    assert parsed.meta.proj_id == "PROJ1"
    assert parsed.meta.proj_name == "Synthetic CPM Fixture"
    assert parsed.meta.data_date is not None
    assert parsed.meta.data_date.isoformat() == "2026-01-05T08:00:00"
    assert parsed.meta.clndr_id == "CAL1"


def test_parses_calendar_work_week():
    parsed = parse_xer(_load())
    assert len(parsed.calendars) == 1
    cal = parsed.calendars[0]
    assert cal.clndr_id == "CAL1"
    assert cal.hours_per_day == pytest.approx(9.0)

    working_days = {d.day_of_week for d in cal.default_work_week if d.is_working}
    assert working_days == {1, 2, 3, 4, 5}  # Mon-Fri, P6 convention (0=Sun)

    monday = next(d for d in cal.default_work_week if d.day_of_week == 1)
    assert monday.total_hours == pytest.approx(9.0)


def test_parses_activities_and_relationships():
    parsed = parse_xer(_load())
    assert len(parsed.activities) == 6
    assert len(parsed.relationships) == 6

    by_code = {a.task_code: a for a in parsed.activities}
    assert by_code["A100"].target_drtn_hr_cnt == 8
    assert by_code["A600"].task_type == "TT_FinMile"

    rel = next(r for r in parsed.relationships if r.task_id == "1002")
    assert rel.pred_task_id == "1001"
    assert rel.pred_type == "PR_FS"


def test_rejects_file_with_no_project_table():
    with pytest.raises(XerParseError):
        parse_xer(b"%T\tCALENDAR\n%F\tclndr_id\n")


def test_rejects_oversized_file(monkeypatch):
    import app.parser.xer_parser as xer_parser_module

    monkeypatch.setattr(xer_parser_module, "MAX_FILE_BYTES", 10)
    with pytest.raises(XerParseError):
        parse_xer(_load())
