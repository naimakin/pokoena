from app.engine.diff.logic_diff import compare_relationship_snapshots


def _rel(pred="A", succ="B", link_type="FS", lag_hours=0.0, pred_critical=False, succ_critical=False) -> dict:
    return {
        "pred_external_id": pred,
        "pred_name": f"Activity {pred}",
        "succ_external_id": succ,
        "succ_name": f"Activity {succ}",
        "link_type": link_type,
        "lag_hours": lag_hours,
        "pred_critical": pred_critical,
        "succ_critical": succ_critical,
    }


def test_identical_snapshots_report_no_changes():
    snap = [_rel("A", "B"), _rel("B", "C")]
    summary, changes = compare_relationship_snapshots(snap, snap)

    assert summary == {"added": 0, "removed": 0, "modified": 0, "total": 0}
    assert changes == []


def test_new_relationship_is_added():
    snap_a = [_rel("A", "B")]
    snap_b = [_rel("A", "B"), _rel("B", "C")]

    summary, changes = compare_relationship_snapshots(snap_a, snap_b)

    assert summary["added"] == 1
    added = next(c for c in changes if c.change_type == "ADDED")
    assert (added.pred_external_id, added.succ_external_id) == ("B", "C")
    assert added.new_link_type == "FS"


def test_removed_relationship_reports_prior_criticality():
    snap_a = [_rel("A", "B", pred_critical=True, succ_critical=True)]
    snap_b = []

    summary, changes = compare_relationship_snapshots(snap_a, snap_b)

    assert summary["removed"] == 1
    removed = changes[0]
    assert removed.change_type == "REMOVED"
    assert removed.pred_was_critical is True
    assert removed.succ_was_critical is True
    assert removed.old_link_type == "FS"


def test_link_type_change_is_modified_with_type_changed_flag():
    snap_a = [_rel("A", "B", link_type="FS")]
    snap_b = [_rel("A", "B", link_type="SS")]

    summary, changes = compare_relationship_snapshots(snap_a, snap_b)

    assert summary["modified"] == 1
    change = changes[0]
    assert change.changes == ["TYPE_CHANGED"]
    assert change.old_link_type == "FS"
    assert change.new_link_type == "SS"
    assert change.old_lag_hours is None  # lag didn't change — not reported


def test_lag_change_above_threshold_is_modified():
    snap_a = [_rel("A", "B", lag_hours=0.0)]
    snap_b = [_rel("A", "B", lag_hours=16.0)]

    summary, changes = compare_relationship_snapshots(snap_a, snap_b, lag_threshold_hours=8.0)

    assert summary["modified"] == 1
    change = changes[0]
    assert change.changes == ["LAG_CHANGED"]
    assert change.old_lag_hours == 0.0
    assert change.new_lag_hours == 16.0
    # old_link_type is always populated for context, even when only the lag
    # changed — only new_link_type is gated on type_changed (matches the
    # reference's own asymmetric behavior).
    assert change.old_link_type == "FS"
    assert change.new_link_type is None


def test_lag_change_below_threshold_is_ignored():
    snap_a = [_rel("A", "B", lag_hours=0.0)]
    snap_b = [_rel("A", "B", lag_hours=4.0)]

    summary, changes = compare_relationship_snapshots(snap_a, snap_b, lag_threshold_hours=8.0)

    assert summary == {"added": 0, "removed": 0, "modified": 0, "total": 0}


def test_both_type_and_lag_change_report_both_flags():
    snap_a = [_rel("A", "B", link_type="FS", lag_hours=0.0)]
    snap_b = [_rel("A", "B", link_type="SS", lag_hours=24.0)]

    summary, changes = compare_relationship_snapshots(snap_a, snap_b)

    assert set(changes[0].changes) == {"TYPE_CHANGED", "LAG_CHANGED"}
