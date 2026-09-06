from datetime import date
from types import SimpleNamespace

from app.engine.evm.variance_engine import compute_baseline_date_variance


def _ba(activity_id, start, end, wbs="WBS1"):
    return SimpleNamespace(activity_id=activity_id, baseline_start=start, baseline_end=end, wbs_code=wbs)


def _act(activity_id, *, planned_start=None, planned_finish=None, actual_start=None, actual_finish=None,
         early_start=None, early_finish=None, is_critical=False, status="not_started", pct=0, code="A1", name="Act"):
    return SimpleNamespace(
        id=activity_id, external_id=code, name=name, planned_start=planned_start, planned_finish=planned_finish,
        actual_start=actual_start, actual_finish=actual_finish, early_start=early_start, early_finish=early_finish,
        is_critical=is_critical, status=SimpleNamespace(value=status), percent_complete=pct,
    )


def test_on_baseline_reports_zero_variance():
    ba = [_ba("a", date(2026, 1, 5), date(2026, 1, 9))]
    acts = {"a": _act("a", planned_start=date(2026, 1, 5), planned_finish=date(2026, 1, 9))}

    result = compute_baseline_date_variance(ba, acts)

    row = result["rows"][0]
    assert row["start_variance_days"] == 0
    assert row["finish_variance_days"] == 0
    assert result["summary"]["behind"] == 0
    assert result["summary"]["on_track"] == 1
    assert result["summary"]["project_finish_variance_days"] == 0


def test_slip_is_positive_and_counts_as_behind():
    ba = [_ba("a", date(2026, 1, 5), date(2026, 1, 9))]
    acts = {"a": _act("a", planned_start=date(2026, 1, 8), planned_finish=date(2026, 1, 19), is_critical=True)}

    result = compute_baseline_date_variance(ba, acts)

    row = result["rows"][0]
    assert row["start_variance_days"] == 3
    assert row["finish_variance_days"] == 10
    summary = result["summary"]
    assert summary["behind"] == 1
    assert summary["worst_slip_days"] == 10
    assert summary["critical_slip_count"] == 1
    assert summary["project_finish_variance_days"] == 10
    hist = {b["label"]: b["count"] for b in summary["finish_variance_histogram"]}
    assert hist["1-30 days late"] == 1


def test_actual_dates_win_over_planned():
    ba = [_ba("a", date(2026, 1, 5), date(2026, 1, 9))]
    acts = {"a": _act("a", planned_finish=date(2026, 1, 20), actual_finish=date(2026, 1, 7), pct=100)}

    result = compute_baseline_date_variance(ba, acts)

    assert result["rows"][0]["finish_variance_days"] == -2
    assert result["summary"]["ahead"] == 1


def test_activity_missing_from_live_schedule_is_skipped():
    ba = [_ba("a", date(2026, 1, 5), date(2026, 1, 9)), _ba("gone", date(2026, 1, 5), date(2026, 1, 9))]
    acts = {"a": _act("a", planned_start=date(2026, 1, 5), planned_finish=date(2026, 1, 9))}

    result = compute_baseline_date_variance(ba, acts)

    assert result["summary"]["activities_total"] == 1
