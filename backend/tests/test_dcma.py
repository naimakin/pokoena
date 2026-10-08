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
    a = _act(external_id="A1", constraint_type="CS_MANDSTART")
    report = run_dcma([a], [], hours_per_day=8, data_date=None)

    hard = next(c for c in report.checks if c.id == 5)
    assert hard.status == "fail"
    assert hard.details == ["A1"]


def test_on_or_after_constraints_are_not_hard():
    # P6's "start / finish on or after" are soft floors, not mandatory dates.
    acts = [_act(external_id="A1", constraint_type="CS_MSOA"), _act(external_id="A2", constraint_type="CS_MEOA")]
    report = run_dcma(acts, [], hours_per_day=8, data_date=None)

    hard = next(c for c in report.checks if c.id == 5)
    assert hard.details == []


def test_secondary_constraint_also_flagged():
    a = _act(external_id="A1", constraint_type_2="CS_MANDFIN")
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


# --- #15 Out of sequence (POKO's own check, unscored) ---------------------

_P6 = {"done": "TK_Complete", "ip": "TK_Active", "ns": "TK_NotStart"}


def _oos(pairs: list[tuple[str, str, LinkType]], states: dict[str, str], **kwargs):
    acts = {code: _act(external_id=code, status_code=_P6[s]) for code, s in states.items()}
    rels = [_rel(acts[p], acts[s], lt) for p, s, lt in pairs]
    report = run_dcma(list(acts.values()), rels, hours_per_day=8, data_date=None, **kwargs)
    return report, next(c for c in report.checks if c.id == 15)


def test_oos_completed_with_unfinished_fs_predecessor():
    _, c = _oos([("P", "A", LinkType.FS)], {"P": "ip", "A": "done"})
    assert c.details == ["P / FS / A"]
    assert c.status == "warn"


def test_oos_completed_with_unfinished_ff_predecessor():
    _, c = _oos([("P", "A", LinkType.FF)], {"P": "ns", "A": "done"})
    assert c.details == ["P / FF / A"]


def test_oos_in_progress_with_unfinished_fs_predecessor():
    _, c = _oos([("P", "A", LinkType.FS)], {"P": "ip", "A": "ip"})
    assert c.details == ["P / FS / A"]


def test_oos_in_progress_with_not_started_ss_predecessor():
    _, c = _oos([("P", "A", LinkType.SS)], {"P": "ns", "A": "ip"})
    assert c.details == ["P / SS / A"]


def test_oos_in_progress_ss_predecessor_already_started_is_fine():
    _, c = _oos([("P", "A", LinkType.SS)], {"P": "ip", "A": "ip"})
    assert c.details == []
    assert c.status == "pass"


def test_oos_negatives():
    _, c = _oos(
        [
            ("P1", "A1", LinkType.FS),  # completed predecessor
            ("P2", "A2", LinkType.SS),  # SS on a completed activity
            ("P3", "A3", LinkType.SF),  # SF never counts
            ("P4", "A4", LinkType.FF),  # FF on an in-progress activity
            ("P5", "A5", LinkType.FS),  # not-started activity
        ],
        {
            "P1": "done", "A1": "done",
            "P2": "ns", "A2": "done",
            "P3": "ns", "A3": "done",
            "P4": "ns", "A4": "ip",
            "P5": "ns", "A5": "ns",
        },
    )
    assert c.details == []


def test_oos_lists_every_offending_link_of_an_activity():
    _, c = _oos(
        [("P2", "A", LinkType.FS), ("P1", "A", LinkType.FF)],
        {"P1": "ns", "P2": "ip", "A": "done"},
    )
    assert c.details == ["P1 / FF / A", "P2 / FS / A"]
    assert c.value == 2


def test_oos_completed_finish_milestone_counts():
    p = _act(external_id="P", status_code="TK_Active")
    m = _act(external_id="M", status_code="TK_Complete", task_type="TT_FinMile")
    report = run_dcma([p, m], [_rel(p, m)], hours_per_day=8, data_date=None)
    assert next(c for c in report.checks if c.id == 15).details == ["P / FS / M"]


def test_oos_is_not_scored():
    report, c = _oos([("P", "A", LinkType.FS)], {"P": "ip", "A": "done"})
    assert c.scored is False and c.status == "warn"
    scored = [x for x in report.checks if x.scored and x.status != "not_tracked"]
    points = sum(1.0 if x.status == "pass" else 0.5 if x.status == "warn" else 0.0 for x in scored)
    assert report.overall_score == round(points / len(scored) * 100, 1)


def test_oos_any_finding_warns_and_lists_every_link():
    # No target and no 20-row cap: the analyst wants every link reported.
    states = {"P": "ns", **{f"A{i:02d}": "done" for i in range(30)}}
    pairs = [("P", f"A{i:02d}", LinkType.FS) for i in range(30)]
    _, c = _oos(pairs, states)
    assert c.status == "warn"
    assert len(c.details) == 30
    assert c.details[0] == "P / FS / A00"


def test_oos_stored_target_from_an_older_version_is_ignored():
    from app.engine.quality.dcma import DcmaThresholds

    t = DcmaThresholds.from_overrides({"out_of_sequence_max": 6.5})
    _, c = _oos([("P", "A", LinkType.FS)], {"P": "ip", "A": "done"}, thresholds=t)
    assert c.status == "warn"


# --- #16 Actuals after data date (POKO's own check, unscored) --------------


def _c16(acts, dd=datetime(2026, 9, 25)):
    report = run_dcma(acts, [], hours_per_day=8, data_date=dd)
    return report, next(c for c in report.checks if c.id == 16)


def test_actuals_after_data_date_lists_start_and_finish():
    a = _act(external_id="A", status_code="TK_Complete", actual_start=date(2026, 9, 20), actual_finish=date(2026, 9, 30))
    b = _act(external_id="B", status_code="TK_Active", actual_start=date(2026, 10, 2))
    _, c = _c16([a, b])
    assert c.status == "warn"
    assert c.details == ["B / Actual start / 2026-10-02 / 7", "A / Actual finish / 2026-09-30 / 5"]
    assert c.value == 2


def test_actuals_on_or_before_data_date_pass():
    a = _act(external_id="A", status_code="TK_Complete", actual_start=date(2026, 9, 1), actual_finish=date(2026, 9, 25))
    _, c = _c16([a])
    assert c.status == "pass"
    assert c.details == []


def test_actuals_both_dates_count_the_activity_once():
    a = _act(external_id="A", status_code="TK_Complete", actual_start=date(2026, 9, 26), actual_finish=date(2026, 9, 27))
    _, c = _c16([a])
    assert len(c.details) == 2
    assert c.value == 1


def test_actuals_after_data_date_is_not_scored():
    a = _act(external_id="A", status_code="TK_Active", actual_start=date(2026, 10, 2))
    report, c = _c16([a])
    assert c.scored is False
    scored = [x for x in report.checks if x.scored and x.status != "not_tracked"]
    points = sum(1.0 if x.status == "pass" else 0.5 if x.status == "warn" else 0.0 for x in scored)
    assert report.overall_score == round(points / len(scored) * 100, 1)
