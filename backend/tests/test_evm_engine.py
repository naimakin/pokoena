import uuid
from datetime import date, datetime

from app.engine.evm.evm_engine import calculate_evm
from app.models.activity import Activity
from app.models.resource_assignment import ResourceAssignment


def _act(**kwargs) -> Activity:
    defaults = dict(
        id=uuid.uuid4(),
        external_id="A1",
        name="Activity A1",
        status_code="TK_Active",
        percent_complete=0,
    )
    defaults.update(kwargs)
    return Activity(**defaults)


def _assignment(activity: Activity, target_qty: float, act_reg_qty: float = 0.0) -> ResourceAssignment:
    return ResourceAssignment(
        id=uuid.uuid4(),
        activity_id=activity.id,
        resource_id=uuid.uuid4(),
        remain_qty=max(target_qty - act_reg_qty, 0),
        target_qty=target_qty,
        act_reg_qty=act_reg_qty,
        target_cost=0.0,
        act_reg_cost=0.0,
        remain_cost=0.0,
    )


def test_bac_is_sum_of_target_qty_across_assignments():
    a = _act(percent_complete=0)
    assignments = [_assignment(a, 20.0), _assignment(a, 20.0)]

    result = calculate_evm([a], assignments, [], None)

    assert result.bac == 40.0
    assert result.activity_results[0].bac == 40.0


def test_ev_is_bac_times_percent_complete():
    a = _act(percent_complete=50)
    assignments = [_assignment(a, 40.0)]

    result = calculate_evm([a], assignments, [], None)

    assert result.ev == 20.0


def test_ac_is_sum_of_actual_qty():
    a = _act()
    assignments = [_assignment(a, 40.0, act_reg_qty=10.0), _assignment(a, 0.0, act_reg_qty=5.0)]

    result = calculate_evm([a], assignments, [], None)

    assert result.ac == 15.0


def test_no_assignments_gives_zero_bac_and_none_indices():
    a = _act(percent_complete=50)

    result = calculate_evm([a], [], [], None)

    activity_result = result.activity_results[0]
    assert activity_result.bac == 0.0
    assert activity_result.ev == 0.0
    assert activity_result.cpi is None  # AC=0 -> division undefined, not zero
    assert activity_result.spi is None  # PV=0 -> division undefined, not zero


def test_planned_pct_linear_fallback_without_calendar():
    a = _act(
        percent_complete=0,
        planned_start=date(2026, 1, 1),
        planned_finish=date(2026, 1, 11),  # 10-day span
    )
    assignments = [_assignment(a, 100.0)]
    data_date = datetime(2026, 1, 6)  # halfway through

    result = calculate_evm([a], assignments, [], data_date)

    # No calendar supplied -> linear fallback: ~50% of the span elapsed.
    assert result.activity_results[0].pv == 50.0


def test_burned_hours_override_replaces_ac_and_recomputes_dependents():
    a = _act(percent_complete=50)
    assignments = [_assignment(a, 40.0, act_reg_qty=10.0)]

    result = calculate_evm([a], assignments, [], None, burned_hours={a.id: 25.0})

    activity_result = result.activity_results[0]
    assert activity_result.ac == 25.0
    assert activity_result.cv == activity_result.ev - 25.0
    assert activity_result.cpi == round(activity_result.ev / 25.0, 6)


def test_project_rollup_sums_across_activities():
    a = _act(external_id="A1", percent_complete=100)
    b = _act(external_id="A2", percent_complete=0)
    assignments = [_assignment(a, 20.0, act_reg_qty=20.0), _assignment(b, 30.0)]

    result = calculate_evm([a, b], assignments, [], None)

    assert result.bac == 50.0
    assert result.ev == 20.0
    assert result.ac == 20.0
    assert len(result.activity_results) == 2
