"""CPM scheduler test against a hand-computed synthetic network:

    A100 (1d) -> A200 (5d) -> A300 (3d) -> A600 (finish milestone)
    A100 (1d) -> A400 (1d) -> A500 (2d) -----------^

Calendar: Mon-Fri, 08:00-17:00 (9h/day). Data date: Mon 2026-01-05 08:00.
Path A100-A200-A300-A600 is critical (72 work-hours); the A400-A500 branch
carries 40 work-hours of float. Expected dates below were computed by hand
by walking CalendarEngine.add_work_hours/sub_work_hours day-by-day — see the
plan/commit history for the full worked calculation.
"""

from datetime import datetime
from pathlib import Path

import pytest

from app.engine.cpm.scheduler import schedule
from app.parser.xer_parser import parse_xer

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


@pytest.fixture()
def scheduled():
    parsed = parse_xer(FIXTURE.read_bytes())
    schedule(parsed)
    return {a.task_code: a for a in parsed.activities}


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_critical_path_dates(scheduled):
    a100, a200, a300, a600 = scheduled["A100"], scheduled["A200"], scheduled["A300"], scheduled["A600"]

    assert a100.early_start_date == _dt("2026-01-05T08:00")
    assert a100.early_end_date == _dt("2026-01-05T16:00")

    assert a200.early_start_date == _dt("2026-01-05T16:00")
    assert a200.early_end_date == _dt("2026-01-12T11:00")

    assert a300.early_start_date == _dt("2026-01-12T11:00")
    assert a300.early_end_date == _dt("2026-01-14T17:00")

    assert a600.early_start_date == _dt("2026-01-14T17:00")
    assert a600.early_end_date == _dt("2026-01-14T17:00")


def test_float_bearing_branch_dates(scheduled):
    a400, a500 = scheduled["A400"], scheduled["A500"]

    assert a400.early_start_date == _dt("2026-01-05T16:00")
    assert a400.early_end_date == _dt("2026-01-06T15:00")

    assert a500.early_start_date == _dt("2026-01-06T15:00")
    assert a500.early_end_date == _dt("2026-01-08T13:00")


def test_total_float_and_criticality(scheduled):
    for code in ("A100", "A200", "A300", "A600"):
        act = scheduled[code]
        assert act.tf_days == pytest.approx(0.0, abs=1e-6), code
        assert act.lp_critical is True, code

    for code in ("A400", "A500"):
        act = scheduled[code]
        assert act.total_float_hr_cnt == pytest.approx(40.0), code
        assert act.lp_critical is False, code


def test_project_finish_matches_critical_path_end(scheduled):
    assert scheduled["A600"].early_end_date == scheduled["A300"].early_end_date


# --- drivers, Retained Logic, Expected Finish (Schedule Simulation) ----------


def _fresh():
    parsed = parse_xer(FIXTURE.read_bytes())
    return parsed, {a.task_code: a for a in parsed.activities}


def test_forward_pass_records_what_drives_each_activity(scheduled):
    assert scheduled["A100"].driven_by == "data_date"
    assert scheduled["A300"].driven_by == "logic"
    assert scheduled["A300"].driving_rels == [(scheduled["A200"].task_id, "PR_FS", 0.0)]
    # Both branches meet at A600; only the critical one drives it.
    assert [r[0] for r in scheduled["A600"].driving_rels] == [scheduled["A300"].task_id]


def test_retained_logic_holds_out_of_sequence_work_for_its_predecessor():
    def run(retained_logic):
        parsed, acts = _fresh()
        a200 = acts["A200"]
        a200.status_code, a200.act_start_date, a200.remain_drtn_hr_cnt = "TK_Active", _dt("2026-01-05T08:00"), 20.0
        schedule(parsed, retained_logic=retained_logic)
        return acts

    override = run(False)["A200"]
    assert override.early_end_date == _dt("2026-01-07T10:00")  # data date + 20h, ignoring A100

    retained = run(True)
    a200 = retained["A200"]
    assert a200.restart_date == _dt("2026-01-05T16:00")  # waits for A100
    assert a200.early_end_date == _dt("2026-01-08T09:00")
    assert a200.driven_by == "logic" and a200.driving_rels[0][0] == retained["A100"].task_id
    # In-progress float is late finish - early finish.
    assert a200.total_float_hr_cnt == pytest.approx(0.0)


def test_retained_logic_never_lets_finished_work_push_past_the_data_date():
    def run(retained_logic):
        parsed, acts = _fresh()
        a100 = acts["A100"]
        a100.status_code = "TK_Complete"
        a100.act_start_date, a100.act_end_date = _dt("2026-01-05T08:00"), _dt("2026-01-07T17:00")
        schedule(parsed, retained_logic=retained_logic)
        return acts["A200"]

    assert run(False).early_start_date == _dt("2026-01-07T17:00")
    held = run(True)
    assert held.early_start_date == _dt("2026-01-05T08:00")
    assert held.driven_by == "data_date"


def test_expected_finish_sizes_the_remaining_work():
    parsed, acts = _fresh()
    acts["A300"].expect_end_date = _dt("2026-01-20T17:00")
    schedule(parsed, retained_logic=True)

    assert acts["A300"].early_end_date == _dt("2026-01-20T17:00")
    assert acts["A600"].early_end_date == _dt("2026-01-20T17:00")
