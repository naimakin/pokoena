from datetime import date

from app.engine.evm.progress_engine import (
    VersionRow,
    actual_percent,
    planned_fraction,
    planned_percent,
    schedule_performance,
    version_facts,
    wbs_levels,
)
from app.engine.evm.scurve_engine import compute_evm_series


def test_planned_fraction_counts_days_before_the_data_date():
    # 10-day activity (1st..10th inclusive); data date the 6th = 5 days statused.
    assert planned_fraction(date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 6)) == 0.5
    assert planned_fraction(date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 1)) == 0.0
    assert planned_fraction(date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 11)) == 1.0
    assert planned_fraction(None, date(2026, 1, 10), date(2026, 1, 11)) == 0.0


def test_planned_percent_is_duration_weighted_and_ignores_zero_duration_rows():
    rows = [
        (80.0, date(2026, 1, 1), date(2026, 1, 10)),  # half planned done -> 40h
        (20.0, date(2026, 1, 1), date(2026, 1, 2)),  # fully planned done -> 20h
        (0.0, date(2026, 1, 1), date(2026, 1, 1)),  # milestone, weightless
    ]
    assert planned_percent(rows, date(2026, 1, 6)) == 60.0


def test_planned_percent_mid_project_is_not_100():
    # Regression: the report used to show 100 % planned mid-project because it
    # read the PV curve's last day (baseline finish) instead of the data date.
    rows = [(1000.0, date(2025, 10, 6), date(2027, 1, 28))]
    pct = planned_percent(rows, date(2026, 9, 16))
    assert 70 < pct < 75


def test_actual_percent_and_spi():
    actual = actual_percent([(80.0, 25), (20.0, 100)])  # 20 + 20 of 100
    assert actual == 40.0
    assert schedule_performance(62.42, 38.29) == round(38.29 / 62.42, 4)


def test_spi_zero_state_before_the_baseline_plans_any_work():
    assert schedule_performance(0.0, 0.0) == 1.0
    assert schedule_performance(None, 10.0) is None


def test_version_facts_counts_milestones_tasks_and_wbs_depth():
    rows = [
        VersionRow("TT_Mile", date(2026, 1, 1), date(2026, 1, 1), 2, False),
        VersionRow("TT_FinMile", date(2026, 6, 1), date(2026, 6, 1), 2, True),
        VersionRow("TT_Task", date(2026, 1, 2), date(2026, 3, 1), 4, True),
        VersionRow("TT_LOE", date(2025, 1, 1), date(2028, 1, 1), 9, True),  # ignored
        VersionRow("TT_WBS", date(2025, 1, 1), date(2028, 1, 1), 9, True),  # ignored
    ]
    facts = version_facts(rows)
    assert (facts.milestones_total, facts.milestones_remaining) == (2, 1)
    assert (facts.tasks_total, facts.tasks_remaining) == (1, 1)
    assert facts.max_wbs_level == 4
    assert facts.start == date(2026, 1, 1)
    assert facts.finish == date(2026, 6, 1)


def test_evm_series_carries_cumulative_values_forward():
    pv = {date(2026, 1, 1): 10.0, date(2026, 1, 2): 20.0}
    ac = {date(2026, 1, 1): 5.0, date(2026, 1, 3): 9.0}
    points = {p.snapshot_date: p for p in compute_evm_series(pv, ac, bac=20.0, current_ev=8.0)}
    assert points[date(2026, 1, 2)].ac_cumulative == 5.0  # no entry that day
    assert points[date(2026, 1, 3)].pv_cumulative == 20.0  # past the curve's end


def test_wbs_levels_count_the_project_root_as_level_one():
    levels = wbs_levels({"P": None, "A": "P", "B": "A", "C": "B", "X": "Y", "Y": "X"})
    assert levels["P"] == 1
    assert levels["C"] == 4
    assert levels["X"] == 2  # a malformed cycle stops instead of looping


def test_forecast_keeps_earned_work_and_spreads_the_rest_after_the_data_date():
    from app.engine.evm.progress_engine import forecast_percent

    dd = date(2026, 1, 11)
    rows = [
        (100.0, 50, date(2026, 1, 1), date(2026, 1, 20)),  # 50h earned, 50h over 11th..20th
        (100.0, 0, date(2026, 1, 21), date(2026, 1, 30)),
    ]
    assert forecast_percent(rows, dd, dd) == 25.0
    assert forecast_percent(rows, dd, date(2026, 1, 21)) == 50.0
    assert forecast_percent(rows, dd, date(2026, 2, 1)) == 100.0


def test_update_cadence_is_the_median_recent_gap():
    from app.engine.evm.progress_engine import update_cadence_days

    dates = [date(2026, 1, 1), date(2026, 1, 29), date(2026, 2, 26), date(2026, 3, 5), date(2026, 3, 5)]
    assert update_cadence_days(dates) == 28
    assert update_cadence_days([date(2026, 1, 1)]) is None
