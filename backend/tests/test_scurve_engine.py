import uuid
from datetime import date

from app.engine.evm.scurve_engine import (
    EvmPoint,
    aggregate_granularity,
    compute_current_ev,
    compute_evm_series,
    find_out_of_sequence_activities,
    generate_pv_curve,
)
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship, LinkType


def _act(**kwargs) -> Activity:
    defaults = dict(id=uuid.uuid4(), external_id="A1", percent_complete=0, target_duration_hours=0.0)
    defaults.update(kwargs)
    return Activity(**defaults)


def test_evm_point_pmi_zero_state_before_any_work():
    point = EvmPoint.compute(date(2026, 1, 1), pv_cum=0.0, ev_cum=0.0, ac_cum=0.0, bac=100.0)

    assert point.spi == 1.0
    assert point.cpi == 1.0
    assert point.sv == 0.0
    assert point.cv == 0.0


def test_evm_point_normal_case():
    point = EvmPoint.compute(date(2026, 1, 10), pv_cum=50.0, ev_cum=40.0, ac_cum=50.0, bac=100.0)

    assert point.spi == 0.8  # 40/50
    assert point.cpi == 0.8  # 40/50
    assert point.sv == -10.0
    assert point.cv == -10.0
    assert point.eac == 125.0  # 100/0.8
    assert point.percent_complete_earned == 40.0


def test_evm_point_tcpi_critical_flag():
    # bac=100, ac_cum=50 -> remaining budget=50; needing (100-40)=60 worth of
    # work from 50 remaining budget -> TCPI=1.2 > 1.10 threshold.
    point = EvmPoint.compute(date(2026, 1, 10), pv_cum=50.0, ev_cum=40.0, ac_cum=50.0, bac=100.0)

    assert point.tcpi == 1.2
    assert point.tcpi_critical is True


def test_generate_pv_curve_linear_distribution():
    activities = [{"planned_manhours": 100.0, "baseline_start": date(2026, 1, 1), "baseline_end": date(2026, 1, 10)}]

    curve = generate_pv_curve(activities, bac=100.0)

    assert len(curve) == 10  # Jan 1 through Jan 10 inclusive
    assert curve[0][1] == 10.0  # 100mh / 10 days
    assert curve[-1][2] == 100.0  # cumulative reaches full BAC on the last day


def test_generate_pv_curve_empty_when_bac_zero():
    activities = [{"planned_manhours": 100.0, "baseline_start": date(2026, 1, 1), "baseline_end": date(2026, 1, 10)}]

    assert generate_pv_curve(activities, bac=0.0) == []


def test_generate_pv_curve_skips_activities_missing_dates():
    activities = [{"planned_manhours": 100.0, "baseline_start": None, "baseline_end": None}]

    assert generate_pv_curve(activities, bac=100.0) == []


def test_compute_current_ev_weighted_by_duration():
    a = _act(external_id="A1", percent_complete=50, target_duration_hours=40.0)
    b = _act(external_id="A2", percent_complete=100, target_duration_hours=10.0)

    ev = compute_current_ev([a, b])

    assert ev == 30.0  # 0.5*40 + 1.0*10


def test_compute_evm_series_projects_ev_from_first_actual_date():
    pv_series = {date(2026, 1, 1): 10.0, date(2026, 1, 2): 20.0, date(2026, 1, 3): 30.0}
    ac_series = {date(2026, 1, 2): 15.0}  # actuals only start on day 2

    points = compute_evm_series(pv_series, ac_series, bac=100.0, current_ev=25.0)

    by_date = {p.snapshot_date: p for p in points}
    assert by_date[date(2026, 1, 1)].ev_cumulative == 0.0  # before first actual
    assert by_date[date(2026, 1, 2)].ev_cumulative == 25.0  # from first actual onward
    assert by_date[date(2026, 1, 3)].ev_cumulative == 25.0


def test_aggregate_granularity_weekly_takes_last_point_per_week():
    points = [
        EvmPoint.compute(date(2026, 1, 5), 10, 10, 10, 100),  # Monday, ISO week 2
        EvmPoint.compute(date(2026, 1, 6), 20, 20, 20, 100),  # Tuesday, same week
        EvmPoint.compute(date(2026, 1, 12), 30, 30, 30, 100),  # next Monday, new week
    ]

    weekly = aggregate_granularity(points, "weekly")

    assert len(weekly) == 2
    assert weekly[0].snapshot_date == date(2026, 1, 6)  # last point of week 1
    assert weekly[1].snapshot_date == date(2026, 1, 12)


def test_aggregate_granularity_daily_is_passthrough():
    points = [EvmPoint.compute(date(2026, 1, 1), 10, 10, 10, 100)]

    assert aggregate_granularity(points, "daily") == points


def test_find_out_of_sequence_flags_activity_with_incomplete_predecessor():
    pred = _act(external_id="P1", percent_complete=0)
    succ = _act(external_id="S1", percent_complete=50)
    rel = ActivityRelationship(
        id=uuid.uuid4(), predecessor_id=pred.id, successor_id=succ.id, link_type=LinkType.FS, lag_days=0
    )

    result = find_out_of_sequence_activities([pred, succ], [rel], reported_activity_ids={succ.id})

    assert result == {succ.id}


def test_find_out_of_sequence_ignores_activities_with_no_progress():
    pred = _act(external_id="P1", percent_complete=0)
    succ = _act(external_id="S1", percent_complete=0)  # no progress reported yet
    rel = ActivityRelationship(
        id=uuid.uuid4(), predecessor_id=pred.id, successor_id=succ.id, link_type=LinkType.FS, lag_days=0
    )

    result = find_out_of_sequence_activities([pred, succ], [rel], reported_activity_ids={succ.id})

    assert result == set()


def test_find_out_of_sequence_ignores_when_predecessor_complete():
    pred = _act(external_id="P1", percent_complete=100)
    succ = _act(external_id="S1", percent_complete=50)
    rel = ActivityRelationship(
        id=uuid.uuid4(), predecessor_id=pred.id, successor_id=succ.id, link_type=LinkType.FS, lag_days=0
    )

    result = find_out_of_sequence_activities([pred, succ], [rel], reported_activity_ids={succ.id})

    assert result == set()
