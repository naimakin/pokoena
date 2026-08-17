import uuid
from datetime import date, datetime

import pytest

from app.engine.risk.monte_carlo import ActivityRiskOverride, run_monte_carlo
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship, LinkType


def _act(**kwargs) -> Activity:
    defaults = dict(
        id=uuid.uuid4(),
        external_id="A1",
        task_type="TT_Task",
        status_code="TK_NotStart",
        remaining_duration_hours=8.0,
        target_duration_hours=8.0,
    )
    defaults.update(kwargs)
    return Activity(**defaults)


def _rel(pred: Activity, succ: Activity, link_type: LinkType = LinkType.FS, lag_hours: int = 0) -> ActivityRelationship:
    return ActivityRelationship(
        id=uuid.uuid4(), predecessor_id=pred.id, successor_id=succ.id, link_type=link_type, lag_days=0, lag_hours=lag_hours
    )


def test_all_complete_short_circuits_to_deterministic_result():
    a = _act(external_id="A1", status_code="TK_Complete", actual_finish=date(2026, 1, 10))
    b = _act(external_id="A2", status_code="TK_Complete", actual_finish=date(2026, 1, 15))

    result = run_monte_carlo([a, b], [], {}, 8.0, None, iterations=100)

    expected = datetime(2026, 1, 15)
    assert result.project_finish_p10 == expected
    assert result.project_finish_p50 == expected
    assert result.project_finish_p90 == expected
    assert result.mean_finish == expected
    assert result.critical_activities == []


def test_empty_activities_raises():
    with pytest.raises(ValueError):
        run_monte_carlo([], [], {}, 8.0, None)


def test_optimistic_greater_than_pessimistic_override_raises():
    a = _act(external_id="A1")
    override = ActivityRiskOverride(activity_id=a.id, optimistic=100.0, most_likely=50.0, pessimistic=10.0)

    with pytest.raises(ValueError):
        run_monte_carlo([a], [], {}, 8.0, None, overrides=[override])


def test_negative_spread_raises():
    a = _act(external_id="A1")
    with pytest.raises(ValueError):
        run_monte_carlo([a], [], {}, 8.0, None, spread=-0.1)


def test_single_activity_percentiles_are_ordered():
    a = _act(external_id="A1", remaining_duration_hours=40.0, target_duration_hours=40.0)

    result = run_monte_carlo([a], [], {}, 8.0, datetime(2026, 1, 5), iterations=200, spread=0.3)

    assert result.project_finish_p10 <= result.project_finish_p50
    assert result.project_finish_p50 <= result.project_finish_p80
    assert result.project_finish_p80 <= result.project_finish_p90
    assert result.iterations == 200


def test_zero_variance_override_collapses_to_single_point():
    a = _act(external_id="A1")
    override = ActivityRiskOverride(activity_id=a.id, optimistic=16.0, most_likely=16.0, pessimistic=16.0)

    result = run_monte_carlo([a], [], {}, 8.0, datetime(2026, 1, 5), iterations=50, overrides=[override])

    assert result.project_finish_p10 == result.project_finish_p90
    assert result.project_finish_p10 == datetime(2026, 1, 7)  # 16h / 8hpd = 2 days from 2026-01-05


def test_milestone_has_zero_variance():
    milestone = _act(
        external_id="MS1", task_type="TT_FinMile", remaining_duration_hours=0.0, target_duration_hours=0.0
    )

    result = run_monte_carlo([milestone], [], {}, 8.0, datetime(2026, 1, 5), iterations=50)

    assert result.project_finish_p10 == result.project_finish_p90 == datetime(2026, 1, 5)


def test_two_activity_chain_reports_the_finish_driving_activity_as_critical():
    a = _act(external_id="A1", remaining_duration_hours=8.0, target_duration_hours=8.0)
    b = _act(external_id="A2", remaining_duration_hours=8.0, target_duration_hours=8.0)

    result = run_monte_carlo([a, b], [_rel(a, b)], {}, 8.0, datetime(2026, 1, 5), iterations=100, spread=0.0)

    # "Critical" here means "finishes within an hour of the project finish
    # date" (ported as-is from the reference), not full CPM critical-path
    # membership — in a straight two-node chain only the last activity's EF
    # equals the project finish; A1 finishes a full day earlier.
    assert set(result.critical_activities) == {"A2"}
