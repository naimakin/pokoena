from app.engine.diff.schedule_diff import compute_schedule_diff


def _a(external_id, **kw):
    return {
        "external_id": external_id,
        "p6_task_id": kw.get("p6_task_id"),
        "name": kw.get("name", external_id),
        "wbs_path": kw.get("wbs_path", "W1"),
        "task_type": kw.get("task_type", "TT_Task"),
        "planned_start": kw.get("planned_start"),
        "planned_finish": kw.get("planned_finish"),
        "early_start": kw.get("early_start"),
        "early_finish": kw.get("early_finish"),
        "actual_start": kw.get("actual_start"),
        "actual_finish": kw.get("actual_finish"),
        "target_duration_hours": kw.get("target_duration_hours"),
        "remaining_duration_hours": kw.get("remaining_duration_hours"),
        "constraint_type": kw.get("constraint_type"),
        "constraint_date": kw.get("constraint_date"),
        "is_critical": kw.get("is_critical", False),
        "is_longest_path": kw.get("is_longest_path", False),
        "total_float_hours": kw.get("total_float_hours"),
        "status": kw.get("status", "in_progress"),
        "percent_complete": kw.get("percent_complete", 20),
    }


def _fields(modified, external_id):
    row = next(m for m in modified if m["external_id"] == external_id)
    return {f["field"]: f for f in row["fields"]}


def test_added_removed():
    d = compute_schedule_diff(
        [_a("A", planned_finish="2026-06-01"), _a("GONE", planned_finish="2026-06-01")],
        [_a("A", planned_finish="2026-06-01"), _a("NEW", planned_finish="2026-07-01")],
        [], [],
    )
    assert [x["external_id"] for x in d["activities"]["added"]] == ["NEW"]
    assert [x["external_id"] for x in d["activities"]["removed"]] == ["GONE"]


def test_rename_by_p6_task_id():
    d = compute_schedule_diff(
        [_a("OLD", p6_task_id="t1", planned_finish="2026-06-01")],
        [_a("NEW", p6_task_id="t1", planned_finish="2026-06-01")],
        [], [],
    )
    assert d["activities"]["renamed"] == [{"old_external_id": "OLD", "new_external_id": "NEW", "name": "NEW"}]
    assert d["activities"]["added"] == [] and d["activities"]["removed"] == []


def test_finish_and_start_and_duration_changes():
    prev = [_a("A", planned_start="2026-06-01", planned_finish="2026-06-10", target_duration_hours=80)]
    curr = [_a("A", planned_start="2026-06-05", planned_finish="2026-06-20", target_duration_hours=120)]
    f = _fields(compute_schedule_diff(prev, curr, [], [])["activities"]["modified"], "A")
    assert f["finish"]["delta_days"] == 10
    assert f["start"]["delta_days"] == 4
    assert f["duration"]["delta_hours"] == 40.0


def test_status_percent_criticality_constraint_wbs():
    prev = [_a("A", planned_finish="2026-06-01", status="not_started", percent_complete=0, is_critical=False, wbs_path="W1")]
    curr = [_a("A", planned_finish="2026-06-01", status="in_progress", percent_complete=45, is_critical=True,
               wbs_path="W2", constraint_type="CS_MSO", constraint_date="2026-06-15")]
    # prev has constraint_type key (None) so a constraint add IS reported
    prev[0]["constraint_type"] = None
    prev[0]["constraint_date"] = None
    f = _fields(compute_schedule_diff(prev, curr, [], [])["activities"]["modified"], "A")
    assert f["status"]["new"] == "in_progress"
    assert f["percent_complete"]["new"] == 45
    assert f["criticality"]["new"] == "critical"
    assert "CS_MSO" in f["constraint"]["new"]
    assert f["wbs"]["old"] == "W1" and f["wbs"]["new"] == "W2"


def test_threshold_suppresses_small_finish_move():
    prev = [_a("A", planned_finish="2026-06-01")]
    curr = [_a("A", planned_finish="2026-06-02")]
    assert compute_schedule_diff(prev, curr, [], [], date_threshold_days=2)["activities"]["modified"] == []


def test_missing_start_keys_degrade_gracefully():
    # old snapshot without any start key -> no "start" field even though finish moved
    prev = [{"external_id": "A", "p6_task_id": None, "name": "A", "wbs_path": "W1",
             "planned_finish": "2026-06-01", "is_critical": False, "status": "in_progress", "percent_complete": 0}]
    curr = [_a("A", planned_start="2026-06-05", planned_finish="2026-06-20")]
    f = _fields(compute_schedule_diff(prev, curr, [], [])["activities"]["modified"], "A")
    assert "finish" in f and "start" not in f


def test_relationship_changes_delegated():
    rel_prev = [{"pred_external_id": "A", "pred_name": "A", "succ_external_id": "B", "succ_name": "B",
                 "link_type": "FS", "lag_hours": 0}]
    rel_curr = [{"pred_external_id": "A", "pred_name": "A", "succ_external_id": "B", "succ_name": "B",
                 "link_type": "SS", "lag_hours": 0}]
    d = compute_schedule_diff([], [], rel_prev, rel_curr)
    assert d["summary"]["relationships_modified"] == 1
    assert d["relationships"]["changes"][0]["change_type"] == "MODIFIED"
