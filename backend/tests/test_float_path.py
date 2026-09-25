from datetime import date

from app.engine.cpm.float_path import compute_float_paths


def _a(external_id, start_day, finish_day, total_float_hours=0.0, **kw):
    return {
        "external_id": external_id,
        "name": kw.get("name", external_id),
        "wbs_path": kw.get("wbs_path", "W1"),
        "status": kw.get("status", "not_started"),
        "percent_complete": kw.get("percent_complete", 0),
        "early_start": date(2026, 3, start_day),
        "early_finish": date(2026, 3, finish_day),
        "late_start": None,
        "late_finish": None,
        "total_float_hours": total_float_hours,
        "free_float_hours": kw.get("free_float_hours", 0.0),
        "is_critical": total_float_hours <= 0,
        "is_longest_path": kw.get("is_longest_path", total_float_hours <= 0),
    }


def _r(pred, succ, link_type="FS", lag_days=0):
    return {"pred_external_id": pred, "succ_external_id": succ, "link_type": link_type, "lag_days": lag_days}


def _ids(path):
    return [a.external_id for a in path.activities]


def test_path_one_is_the_driving_chain_into_the_chosen_activity():
    acts = [_a("A", 1, 5), _a("B", 6, 10), _a("MS", 11, 11), _a("SIDE", 1, 3, total_float_hours=40.0)]
    rels = [_r("A", "B"), _r("B", "MS"), _r("SIDE", "MS")]

    result = compute_float_paths(acts, rels, "MS", path_count=3)

    assert _ids(result.paths[0]) == ["A", "B", "MS"]
    assert result.paths[0].total_float_days == 0.0
    # Chronological order, and each row carries the link that drove it in.
    assert [a.link_type for a in result.paths[0].activities] == [None, "FS", "FS"]


def test_later_paths_branch_off_and_say_where_they_join():
    acts = [_a("A", 1, 5), _a("B", 6, 10), _a("MS", 11, 11), _a("SIDE", 1, 3, total_float_hours=40.0)]
    rels = [_r("A", "B"), _r("B", "MS"), _r("SIDE", "MS")]

    result = compute_float_paths(acts, rels, "MS", path_count=3)

    assert _ids(result.paths[1]) == ["SIDE"]
    assert result.paths[1].joins_at_external_id == "MS"
    assert result.paths[1].join_link_type == "FS"
    assert result.paths[1].total_float_days == 5.0
    # SIDE finishes 3 Mar, MS starts 11 Mar: 7 days of slack on the link.
    assert result.paths[1].join_gap_days == 7.0
    # Only two chains exist, so asking for three is not a truncation.
    assert result.truncated is False
    assert len(result.paths) == 2


def test_an_activity_is_only_ever_on_one_path():
    #    A → B → MS
    #    A → C → MS   (A is shared; whichever path claims it keeps it)
    acts = [_a("A", 1, 5), _a("B", 6, 10), _a("C", 6, 8, total_float_hours=16.0), _a("MS", 11, 11)]
    rels = [_r("A", "B"), _r("B", "MS"), _r("A", "C"), _r("C", "MS")]

    result = compute_float_paths(acts, rels, "MS", path_count=4)

    seen = [eid for p in result.paths for eid in _ids(p)]
    assert len(seen) == len(set(seen))
    assert _ids(result.paths[0]) == ["A", "B", "MS"]
    assert _ids(result.paths[1]) == ["C"]


def test_free_float_follows_the_tightest_link_not_the_lowest_float():
    # Into MS: P_TIGHT drives it (no slack on the link) but carries 2 days of
    # total float; P_LOOSE has zero total float but 4 days of slack on its link.
    acts = [
        _a("MS", 20, 20),
        _a("P_TIGHT", 10, 19, total_float_hours=16.0),
        _a("P_LOOSE", 10, 15, total_float_hours=0.0),
    ]
    rels = [_r("P_TIGHT", "MS"), _r("P_LOOSE", "MS")]

    result = compute_float_paths(acts, rels, "MS", method="free_float", path_count=1)

    assert _ids(result.paths[0]) == ["P_TIGHT", "MS"]


def test_total_float_returns_float_bands_not_chains():
    # P6's Total Float method bands by float value; band members need not be
    # linked to each other, and the chain structure is ignored entirely.
    acts = [
        _a("MS", 20, 20),
        _a("P_TIGHT", 10, 19, total_float_hours=16.0),
        _a("P_LOOSE", 10, 15, total_float_hours=0.0),
    ]
    rels = [_r("P_TIGHT", "MS"), _r("P_LOOSE", "MS")]

    result = compute_float_paths(acts, rels, "MS", method="total_float", path_count=5)

    assert [(p.total_float_days, _ids(p)) for p in result.paths] == [
        (0.0, ["P_LOOSE", "MS"]),
        (2.0, ["P_TIGHT"]),
    ]
    # Bands carry no driving link, because they are not a chain.
    assert all(a.link_type is None for p in result.paths for a in p.activities)


def test_acceleration_headroom_is_the_gap_to_the_next_path():
    acts = [_a("A", 1, 5), _a("B", 6, 10), _a("MS", 11, 11), _a("SIDE", 1, 3, total_float_hours=40.0)]
    rels = [_r("A", "B"), _r("B", "MS"), _r("SIDE", "MS")]

    result = compute_float_paths(acts, rels, "MS", path_count=3)

    # Path 1 is at 0 days of float, path 2 at 5 — pull path 1 in more than that
    # and path 2 becomes the critical one.
    assert result.acceleration_headroom_days == 5.0


def test_completed_activities_are_left_out_by_default():
    acts = [
        _a("DONE", 1, 5, status="complete", percent_complete=100),
        _a("B", 6, 10),
        _a("MS", 11, 11),
    ]
    rels = [_r("DONE", "B"), _r("B", "MS")]

    assert _ids(compute_float_paths(acts, rels, "MS").paths[0]) == ["B", "MS"]
    assert _ids(compute_float_paths(acts, rels, "MS", exclude_completed=False).paths[0]) == [
        "DONE",
        "B",
        "MS",
    ]


def _weekdays_between(start, end, _clndr_id):
    days, step = 0, start
    while step < end:
        step = step.fromordinal(step.toordinal() + 1)
        if step.weekday() < 5:
            days += 1
    return float(days)


def test_work_days_stop_a_weekend_being_reported_as_slack():
    # A finishes Friday 6 Mar 2026, MS starts Monday 9 Mar. There is no working
    # time in between, but two calendar days.
    acts = [_a("A", 2, 6), _a("MS", 9, 9)]
    rels = [_r("A", "MS")]

    assert compute_float_paths(acts, rels, "MS").paths[0].activities[-1].link_gap_days == 2.0
    by_work = compute_float_paths(acts, rels, "MS", work_days=_weekdays_between)
    assert by_work.paths[0].activities[-1].link_gap_days == 0.0


def test_work_days_change_which_chain_branches_off_first():
    # Two chains feed different points of path 1. FAR's link spans a weekend, so
    # by calendar days it looks slacker than NEAR's and branches second; by
    # working days it is the tighter of the two and goes first.
    # Path 1 is P1A → P1B → MS. FAR feeds MS across two weekends (10 calendar
    # days, 6 working); NEAR feeds P1B across one (9 calendar days, 7 working).
    acts = [
        _a("P1A", 2, 9),
        _a("P1B", 11, 13),
        _a("MS", 16, 16),
        _a("FAR", 2, 6, total_float_hours=8.0),
        _a("NEAR", 2, 2, total_float_hours=8.0),
    ]
    rels = [_r("P1A", "P1B"), _r("P1B", "MS"), _r("FAR", "MS"), _r("NEAR", "P1B")]

    by_calendar = compute_float_paths(acts, rels, "MS", path_count=3)
    by_work = compute_float_paths(acts, rels, "MS", path_count=3, work_days=_weekdays_between)

    assert [_ids(p) for p in by_calendar.paths[1:]] == [["NEAR"], ["FAR"]]
    assert [_ids(p) for p in by_work.paths[1:]] == [["FAR"], ["NEAR"]]


def test_truncated_is_set_when_more_chains_feed_in_than_were_asked_for():
    acts = [_a("MS", 20, 20)] + [
        _a(f"P{i}", 10, 15, total_float_hours=float(i * 8)) for i in range(1, 5)
    ]
    rels = [_r(f"P{i}", "MS") for i in range(1, 5)]

    result = compute_float_paths(acts, rels, "MS", path_count=2)

    assert len(result.paths) == 2
    assert result.truncated is True


def test_lag_and_link_type_are_carried_through_to_the_row():
    acts = [_a("A", 1, 5), _a("B", 10, 14)]
    rels = [_r("A", "B", link_type="SS", lag_days=9)]

    result = compute_float_paths(acts, rels, "B", path_count=1)

    b = result.paths[0].activities[-1]
    assert b.external_id == "B" and b.link_type == "SS" and b.lag_days == 9
    # SS+9 from a 1 Mar start lands exactly on B's 10 Mar start: no slack.
    assert b.link_gap_days == 0.0


def test_a_cycle_does_not_hang_the_walk():
    acts = [_a("A", 1, 5), _a("B", 6, 10)]
    rels = [_r("A", "B"), _r("B", "A")]

    result = compute_float_paths(acts, rels, "B", path_count=2)

    assert _ids(result.paths[0]) == ["A", "B"]


def test_unknown_end_activity_raises():
    try:
        compute_float_paths([_a("A", 1, 5)], [], "NOPE")
    except KeyError as exc:
        assert "NOPE" in str(exc)
    else:
        raise AssertionError("expected KeyError")
