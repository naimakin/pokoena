import uuid
from datetime import date, datetime

from app.engine.quality.dcma import run_dcma
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship, LinkType


def _act(**kwargs) -> Activity:
    defaults = dict(
        id=uuid.uuid4(),
        external_id="A1",
        task_type="TT_Task",
        status_code="TK_NotStart",
        total_float_hours=0.0,
        remaining_duration_hours=8.0,
        is_longest_path=True,
    )
    defaults.update(kwargs)
    return Activity(**defaults)


def _rel(pred: Activity, succ: Activity, link_type: LinkType = LinkType.FS, lag_hours: int = 0) -> ActivityRelationship:
    return ActivityRelationship(
        id=uuid.uuid4(),
        predecessor_id=pred.id,
        successor_id=succ.id,
        link_type=link_type,
        lag_days=0,
        lag_hours=lag_hours,
    )


def test_open_end_activities_fail_logic_check():
    a = _act(external_id="A1")
    b = _act(external_id="A2")
    report = run_dcma([a, b], [], hours_per_day=8, data_date=None)

    logic = next(c for c in report.checks if c.id == 1)
    assert logic.status == "fail"
    assert set(logic.details) == {"A1", "A2"}


def test_milestone_bookended_chain_has_no_open_ends():
    # Milestones are excluded from the open-ends check entirely, and every
    # non-milestone activity in a fully-connected chain has both a
    # predecessor and a successor — see _clean_schedule() below.
    activities, rels = _clean_schedule()
    report = run_dcma(activities, rels, hours_per_day=8, data_date=None)

    logic = next(c for c in report.checks if c.id == 1)
    assert logic.status == "pass"
    assert logic.details == []


def test_negative_float_always_fails():
    a = _act(external_id="A1", total_float_hours=-8.0)
    report = run_dcma([a], [], hours_per_day=8, data_date=None)

    neg = next(c for c in report.checks if c.id == 7)
    assert neg.status == "fail"
    assert neg.details == ["A1"]


def test_high_float_flagged_above_44_working_days():
    a = _act(external_id="A1", total_float_hours=44 * 8 + 1)
    report = run_dcma([a], [], hours_per_day=8, data_date=None)

    high_float = next(c for c in report.checks if c.id == 6)
    assert high_float.status == "fail"
    assert high_float.details == ["A1"]


def test_mandatory_constraint_flagged():
    a = _act(external_id="A1", constraint_type="CS_MSOA")
    report = run_dcma([a], [], hours_per_day=8, data_date=None)

    hard = next(c for c in report.checks if c.id == 5)
    assert hard.status == "fail"
    assert hard.details == ["A1"]


def test_secondary_constraint_also_flagged():
    a = _act(external_id="A1", constraint_type_2="CS_MEOA")
    report = run_dcma([a], [], hours_per_day=8, data_date=None)

    hard = next(c for c in report.checks if c.id == 5)
    assert hard.status == "fail"


def test_zero_float_off_longest_path_is_artificial():
    artificial = _act(external_id="A1", total_float_hours=0.0, is_longest_path=False)
    report = run_dcma([artificial], [], hours_per_day=8, data_date=None)

    artificial_check = next(c for c in report.checks if c.id == 13)
    assert artificial_check.status == "warn"
    assert artificial_check.details == ["A1"]


def test_zero_float_on_longest_path_is_not_artificial():
    genuine = _act(external_id="A1", total_float_hours=0.0, is_longest_path=True)
    report = run_dcma([genuine], [], hours_per_day=8, data_date=None)

    artificial_check = next(c for c in report.checks if c.id == 13)
    assert artificial_check.status == "pass"
    assert artificial_check.details == []


def test_missed_logic_flags_complete_predecessor_with_notstart_successor():
    pred = _act(external_id="P1", status_code="TK_Complete")
    succ = _act(external_id="S1", status_code="TK_NotStart")
    report = run_dcma([pred, succ], [_rel(pred, succ)], hours_per_day=8, data_date=None)

    missed = next(c for c in report.checks if c.id == 11)
    assert missed.status == "fail"
    assert missed.details == ["P1"]


def test_bei_pass_when_on_target():
    on_time = _act(
        external_id="A1", status_code="TK_Complete",
        planned_finish=date(2026, 1, 10), actual_finish=date(2026, 1, 10),
    )
    report = run_dcma([on_time], [], hours_per_day=8, data_date=datetime(2026, 1, 15))

    bei = next(c for c in report.checks if c.id == 14)
    assert bei.status == "pass"
    assert bei.value == 1.0


def test_bei_fails_when_far_behind():
    behind = _act(
        external_id="A1", status_code="TK_NotStart",
        planned_finish=date(2026, 1, 1), actual_finish=None,
    )
    report = run_dcma([behind], [], hours_per_day=8, data_date=datetime(2026, 1, 15))

    bei = next(c for c in report.checks if c.id == 14)
    assert bei.status == "fail"
    assert bei.value == 0.0
    assert bei.details == ["A1"]


def _clean_schedule() -> tuple[list[Activity], list[ActivityRelationship]]:
    """A start/finish milestone bookending a 10-activity chain, with exactly
    one activity on the critical path (10% ≈ DCMA check #12's healthy 5-20%
    band) and the rest carrying float — every other check should pass clean."""
    start = _act(external_id="START", task_type="TT_StartMile", total_float_hours=None, remaining_duration_hours=0.0)
    finish = _act(external_id="FINISH", task_type="TT_FinMile", total_float_hours=None, remaining_duration_hours=0.0)
    critical = _act(external_id="A1", total_float_hours=0.0, is_longest_path=True)
    floats = [_act(external_id=f"A{i}", total_float_hours=100.0, is_longest_path=False) for i in range(2, 11)]

    chain = [start, critical, *floats, finish]
    rels = [_rel(chain[i], chain[i + 1]) for i in range(len(chain) - 1)]
    return chain, rels


def test_resources_check_is_not_tracked_and_excluded_from_score():
    activities, rels = _clean_schedule()
    report = run_dcma(activities, rels, hours_per_day=8, data_date=None)

    resources = next(c for c in report.checks if c.id == 10)
    assert resources.status == "not_tracked"
    # A clean schedule should score 100 across the 13 applicable checks —
    # check #10 must not drag the denominator down.
    assert report.overall_score == 100.0
    assert report.overall_status == "pass"


def test_clean_schedule_scores_100():
    activities, rels = _clean_schedule()
    report = run_dcma(activities, rels, hours_per_day=8, data_date=None)

    assert report.overall_score == 100.0
    assert report.overall_status == "pass"
    assert report.in_scope == 12


def test_resources_check_is_real_when_assignment_ids_provided():
    assigned = _act(external_id="A1")
    unassigned = _act(external_id="A2")
    report = run_dcma(
        [assigned, unassigned], [], hours_per_day=8, data_date=None, assigned_activity_ids={assigned.id}
    )

    resources = next(c for c in report.checks if c.id == 10)
    assert resources.status == "warn"  # 1 of 2 unassigned = 50% > 20% threshold
    assert resources.details == ["A2"]
    assert resources.pct == 50.0
