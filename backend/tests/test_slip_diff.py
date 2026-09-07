from app.engine.diff.slip_diff import compute_slip_between_snapshots


def _snap(external_id, finish, **kw):
    return {
        "external_id": external_id,
        "p6_task_id": kw.get("p6_task_id"),
        "name": kw.get("name", external_id),
        "wbs_path": kw.get("wbs_path"),
        "planned_finish": finish,
        "early_finish": kw.get("early_finish"),
        "actual_finish": kw.get("actual_finish"),
        "is_critical": kw.get("is_critical", False),
        "is_longest_path": kw.get("is_longest_path", False),
        "total_float_hours": kw.get("total_float_hours"),
        "status": kw.get("status", "in_progress"),
        "percent_complete": kw.get("percent_complete", 0),
    }


def test_finish_slip_over_threshold():
    prev = [_snap("A", "2026-06-01")]
    curr = [_snap("A", "2026-06-20")]
    out = compute_slip_between_snapshots(prev, curr, threshold_days=1)
    assert [r["external_id"] for r in out["slipped"]] == ["A"]
    assert out["slipped"][0]["slip_days"] == 19


def test_small_slip_under_threshold_ignored_unless_critical():
    prev = [_snap("A", "2026-06-01"), _snap("B", "2026-06-01", is_critical=True)]
    curr = [_snap("A", "2026-06-02"), _snap("B", "2026-06-02", is_critical=True)]
    out = compute_slip_between_snapshots(prev, curr, threshold_days=1)
    ids = [r["external_id"] for r in out["slipped"]]
    assert ids == ["B"]  # A slipped 1 day (<= threshold), B is critical → bypass


def test_pulled_earlier_is_not_a_slip():
    out = compute_slip_between_snapshots([_snap("A", "2026-06-10")], [_snap("A", "2026-06-01")])
    assert out["slipped"] == []


def test_actual_finish_wins_over_planned():
    prev = [_snap("A", "2026-06-01")]
    curr = [_snap("A", "2026-12-01", actual_finish="2026-05-20")]  # finished early
    out = compute_slip_between_snapshots(prev, curr)
    assert out["slipped"] == []


def test_added_and_removed_buckets():
    prev = [_snap("A", "2026-06-01"), _snap("GONE", "2026-06-01")]
    curr = [_snap("A", "2026-06-01"), _snap("NEW", "2026-07-01")]
    out = compute_slip_between_snapshots(prev, curr)
    assert [x["external_id"] for x in out["added"]] == ["NEW"]
    assert [x["external_id"] for x in out["removed"]] == ["GONE"]


def test_rename_matched_by_p6_task_id():
    prev = [_snap("OLD", "2026-06-01", p6_task_id="t1")]
    curr = [_snap("NEW", "2026-06-20", p6_task_id="t1")]
    out = compute_slip_between_snapshots(prev, curr)
    assert [r["external_id"] for r in out["slipped"]] == ["NEW"]
    assert out["added"] == [] and out["removed"] == []


def test_null_finish_not_slipped():
    out = compute_slip_between_snapshots([_snap("A", None)], [_snap("A", "2026-06-01")])
    assert out["slipped"] == []


def test_sort_critical_first_then_worst():
    prev = [_snap("A", "2026-06-01"), _snap("B", "2026-06-01"), _snap("C", "2026-06-01", is_critical=True)]
    curr = [_snap("A", "2026-06-30"), _snap("B", "2026-06-10"), _snap("C", "2026-06-05", is_critical=True)]
    out = compute_slip_between_snapshots(prev, curr)
    assert [r["external_id"] for r in out["slipped"]] == ["C", "A", "B"]
