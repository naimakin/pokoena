"""QSRA — the risk-driver Monte Carlo (engine/risk/qsra.py), its orchestration
(services/risk_analysis.py) and the Risk section's API.

Engine cases are hand-computed on tiny networks, in working hours from the
data date (0 = data date)."""

from pathlib import Path

import pytest

from app.engine.risk.qsra import (
    FF,
    FS,
    SF,
    SS,
    CorrelationWeights,
    Network,
    RiskDriver,
    SimActivity,
    SimLink,
    inv_impact,
    percentile,
    rank_risks,
    simulate,
)
from app.engine.risk.resource_forecast import AssignmentInput, UpdatePoint, forecast
from app.models.activity import Activity
from tests.test_schedule_import import _setup

FIXTURES = Path(__file__).parent / "fixtures"


def _act(key, hours, status="not_started", **kw):
    return SimActivity(key=key, external_id=key, name=key, status=status, remaining_hours=hours, **kw)


# --- forward pass ---------------------------------------------------------------


def test_forward_pass_link_types_and_lags():
    acts = [_act("A", 16), _act("B", 8), _act("C", 8), _act("D", 8), _act("E", 8)]
    links = [
        SimLink(0, 1, FS, 4),  # B starts 4h after A finishes: 20
        SimLink(0, 2, SS, 8),  # C starts 8h after A starts: 8
        SimLink(0, 3, FF, 0),  # D finishes with A: starts 16 - 8 = 8
        SimLink(0, 4, SF, 24),  # E finishes 24h after A starts: starts 16
    ]
    net = Network(acts, links)
    es, ef = net.forward_pass(net.base)
    assert (es[1], ef[1]) == (20, 28)
    assert (es[2], ef[2]) == (8, 16)
    assert (es[3], ef[3]) == (8, 16)
    assert (es[4], ef[4]) == (16, 24)


def test_in_progress_resumes_at_the_data_date_not_its_actual_start():
    # The old engine finished in-progress work at actual_start + remaining,
    # understating it by the elapsed time.
    net = Network([_act("A", 16, status="active", fixed_start_offset=-80)], [])
    es, ef = net.forward_pass(net.base)
    assert ef[0] == 16


def test_start_and_finish_floors():
    acts = [_act("A", 8), _act("B", 8, start_floor_offset=40), _act("C", 8, finish_floor_offset=100)]
    net = Network(acts, [SimLink(0, 1, FS, 0)])
    es, ef = net.forward_pass(net.base)
    assert es[1] == 40  # the floor beats the logic (8)
    assert ef[2] == 100


def test_completed_predecessors_do_not_hold_up_successors():
    acts = [_act("A", 0, status="complete", fixed_finish_offset=-40), _act("B", 8)]
    net = Network(acts, [SimLink(0, 1, FS, 0)])
    es, ef = net.forward_pass(net.base)
    assert (es[1], ef[1]) == (0, 8)


def test_driving_path_follows_the_longest_chain():
    #   A(8) -> B(40) -> D(8)
    #   A(8) -> C(8)  -> D
    acts = [_act("A", 8), _act("B", 40), _act("C", 8), _act("D", 8)]
    links = [SimLink(0, 1, FS, 0), SimLink(0, 2, FS, 0), SimLink(1, 3, FS, 0), SimLink(2, 3, FS, 0)]
    net = Network(acts, links)
    es, ef = net.forward_pass(net.base)
    assert net.driving_path(es, ef, net.base, 3) == {0, 1, 3}


# --- simulation --------------------------------------------------------------------


def _chain(n=5, hours=40, background=(0.9, 1.0, 1.2)):
    acts = [_act(f"A{i}", hours, background=background) for i in range(n)]
    links = [SimLink(i, i + 1, FS, 0) for i in range(n - 1)]
    return Network(acts, links)


def test_calibration_reproduces_the_deterministic_finish():
    res = simulate(_chain(), [], iterations=50, seed=3)
    assert res.calibration_offset == 200


def test_no_uncertainty_no_risk_is_deterministic():
    res = simulate(_chain(background=(1.0, 1.0, 1.0)), [], iterations=50, seed=3)
    assert set(res.offsets_sorted) == {200.0}


def test_occurrence_rate_matches_probability():
    net = _chain(n=2, background=(1.0, 1.0, 1.0))
    drv = RiskDriver("R-1", "t", 0.3, (1, 2, 3), "triangular", "delay_days", [0])
    res = simulate(net, [drv], iterations=5000, seed=11, track_activities=False)
    assert abs(res.drivers[0].occurred_pct - 30.0) <= 3.0


def test_duration_pct_risk_stretches_every_linked_activity_by_the_same_factor():
    net = _chain(n=2, background=(1.0, 1.0, 1.0))
    drv = RiskDriver("R-1", "t", 1.0, (50, 50, 50), "triangular", "duration_pct", [0, 1])
    res = simulate(net, [drv], iterations=20, seed=1)
    assert set(res.offsets_sorted) == {120.0}  # (40 + 40) × 1.5


def test_delay_days_and_opportunity():
    net = _chain(n=2, background=(1.0, 1.0, 1.0))
    threat = RiskDriver("R-1", "t", 1.0, (2, 2, 2), "triangular", "delay_days", [0])
    res = simulate(net, [threat], iterations=10, seed=1, hours_per_day=8)
    assert set(res.offsets_sorted) == {96.0}  # 80 + 2 days
    opp = RiskDriver("O-1", "o", 1.0, (25, 25, 25), "triangular", "duration_pct", [1], is_opportunity=True)
    res = simulate(net, [opp], iterations=10, seed=1)
    assert set(res.offsets_sorted) == {70.0}  # 40 + 40 × 0.75


def test_common_random_numbers_make_comparisons_clean():
    net = _chain()
    a = RiskDriver("R-1", "t", 0.5, (10, 20, 40), "triangular", "duration_pct", [2])
    b = RiskDriver("R-2", "t", 0.4, (1, 3, 5), "pert", "delay_days", [4])
    one = simulate(net, [a, b], iterations=300, seed=9)
    two = simulate(net, [a, b], iterations=300, seed=9)
    assert one.offsets_sorted == two.offsets_sorted
    # Switching R-2 off can only pull the finish in, iteration by iteration.
    b_off = RiskDriver("R-2", "t", 0.0, (1, 3, 5), "pert", "delay_days", [4])
    without = simulate(net, [a, b_off], iterations=300, seed=9)
    assert percentile(without.offsets_sorted, 80) <= percentile(one.offsets_sorted, 80)


def test_ranking_orders_the_bigger_risk_first():
    net = _chain(background=(1.0, 1.0, 1.0))
    big = RiskDriver("BIG", "t", 0.9, (80, 100, 120), "triangular", "duration_pct", [1])
    small = RiskDriver("SMALL", "t", 0.9, (5, 10, 15), "triangular", "duration_pct", [3])
    p_all, p_bg, ranking = rank_risks(net, [small, big], iterations=300, hours_per_day=8, seed=5)
    assert ranking[0][0] == "BIG"
    assert p_all > p_bg


def test_correlation_widens_the_distribution():
    acts = [_act(f"A{i}", 40, background=(0.8, 1.0, 1.3)) for i in range(30)]
    net = Network(acts, [SimLink(i, i + 1, FS, 0) for i in range(29)])
    independent = simulate(net, [], iterations=600, seed=4, weights=CorrelationWeights(project=0.0, group=0.0),
                           track_activities=False)
    correlated = simulate(net, [], iterations=600, seed=4, weights=CorrelationWeights(project=0.6, group=0.0),
                          track_activities=False)
    assert correlated.sd_offset > independent.sd_offset * 1.5


def test_pert_inverse_is_monotone_and_bounded():
    d = RiskDriver("R", "t", 1.0, (2, 5, 20), "pert")
    values = [inv_impact(d, u / 100) for u in range(101)]
    assert values == sorted(values)
    assert values[0] >= 2 - 1e-9 and values[-1] <= 20 + 1e-9


def test_pert_never_leaves_its_range_at_the_extremes():
    # The tabulated CDF's last entry can land a hair under 1.0, by an amount
    # that depends on the platform's pow() — once, that put u = 1 beyond `high`
    # on Linux CI but not on Windows. Sweep enough shapes to hit it anywhere.
    for low in (0, 1, 2.5, 10):
        for width in (1, 3, 7.7, 18, 55):
            for mode_share in (0.0, 0.1, 0.37, 0.5, 0.83, 1.0):
                high = low + width
                mode = low + width * mode_share
                d = RiskDriver("R", "t", 1.0, (low, mode, high), "pert")
                for u in (0.0, 1e-12, 0.5, 1 - 1e-12, 1.0):
                    v = inv_impact(d, u)
                    assert low <= v <= high, (low, mode, high, u, v)


def test_percentile_interpolates():
    assert percentile([0, 10], 50) == 5
    assert percentile([1, 2, 3, 4, 5], 80) == pytest.approx(4.2)


# --- the CPM fix that came with this ------------------------------------------------


def test_finish_on_or_after_is_a_floor_not_a_mandatory_date():
    """P6's CS_MEOA is 'finish on or after'. Read as a mandatory finish, it pinned
    the late finish to the constraint date, so any activity that logic pushed
    past it showed negative float that P6 doesn't show."""
    from app.engine.cpm.scheduler import schedule
    from app.parser.xer_parser import parse_xer

    text = (FIXTURES / "synthetic_project.xer").read_text("utf-8")
    lines = text.split("\n")
    header = next(line for line in lines if line.startswith("%F\ttask_id"))
    cols = header.split("\t")[1:]
    out = []
    for line in lines:
        if line.startswith("%R\t1003\t"):  # A300, driven well past 2026-01-06 by its predecessors
            cells = line.split("\t")[1:]
            cells[cols.index("cstr_type")] = "CS_MEOA"
            cells[cols.index("cstr_date")] = "2026-01-06 17:00"
            line = "%R\t" + "\t".join(cells)
        out.append(line)
    constrained = parse_xer("\n".join(out).encode("utf-8"))
    schedule(constrained)
    plain = parse_xer(text.encode("utf-8"))
    schedule(plain)

    by_code = {a.task_code: a for a in constrained.activities}
    free = {a.task_code: a for a in plain.activities}
    # The floor is already behind the logic, so it changes nothing: A300 isn't
    # pulled back to the constraint date…
    assert by_code["A300"].early_end_date == free["A300"].early_end_date
    # …and nothing upstream of it goes negative.
    assert all((a.total_float_hr_cnt or 0) >= 0 for a in constrained.activities)


# --- resources ---------------------------------------------------------------------------


def _assign(budget, pct, remaining=None):
    return AssignmentInput("A", budget, budget * pct / 100, budget * (1 - pct / 100) if remaining is None else remaining,
                           pct, None, None, None, None)


def test_resource_forecast_needs_three_periods():
    from datetime import date

    hist = [UpdatePoint("B", date(2026, 1, 5), 0, None), UpdatePoint("U1", date(2026, 1, 19), 100, None)]
    fc = forecast([_assign(1000, 10)], hist, date(2026, 1, 19))
    assert fc.method == "insufficient" and fc.finish_p50 is None


def test_resource_forecast_is_ordered_and_near_the_simple_estimate():
    from datetime import date, timedelta

    d0 = date(2026, 1, 5)
    hist = [UpdatePoint(f"U{k}", d0 + timedelta(weeks=2 * k), 100.0 * k * 2, None) for k in range(5)]
    # 100 units/week demonstrated, 1000 − 800 = 200 left -> about 2 weeks.
    fc = forecast([_assign(1000, 80)], hist, hist[-1].data_date)
    assert fc.method == "demonstrated"
    assert fc.finish_p10 <= fc.finish_p50 <= fc.finish_p90
    assert abs((fc.finish_p50 - hist[-1].data_date).days - 14) <= 1


# --- API ------------------------------------------------------------------------------------


def _login(client):
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})


def _upload(client, project_id, name="synthetic_project.xer"):
    r = client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": (name, (FIXTURES / name).read_bytes(), "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_qsra_run_calibrates_and_measures_a_quantified_risk(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id)

    risk = client.post(f"/projects/{project.id}/risks", json={
        "title": "Late steel", "qsra_enabled": True, "probability_pct": 60, "impact_mode": "duration_pct",
        "impact_min": 20, "impact_ml": 40, "impact_max": 80, "activity_external_ids": ["A300"],
        "post_probability_pct": 20,
    })
    assert risk.status_code == 201, risk.text
    assert risk.json()["probability"] == 4  # 60% -> the 1–5 score follows

    run = client.post(f"/projects/{project.id}/risk/qsra/runs")
    assert run.status_code == 200, run.text
    res = run.json()["results"]
    assert res["model_check"]["calibration_ok"] is True
    assert res["model_check"]["calibration_delta_days"] == 0
    pre = res["pre"]
    assert pre["p10"] <= pre["p50"] <= pre["p80"] <= pre["p90"]
    assert res["drivers"][0]["code"] == risk.json()["code"]
    assert res["drivers"][0]["expected_delay_days"] > 0
    assert res["post"] is not None and res["mitigation_benefit_p80_days"] >= 0
    assert [w["label"] for w in res["waterfall"]][0] == "CPM finish"

    ranked = client.post(f"/projects/{project.id}/risk/qsra/runs/{run.json()['id']}/ranking")
    assert ranked.status_code == 200, ranked.text
    assert ranked.json()["ranking"][0]["code"] == risk.json()["code"]

    latest = client.get(f"/projects/{project.id}/risk/qsra/runs/latest").json()
    assert latest["id"] == run.json()["id"]
    assert len(client.get(f"/projects/{project.id}/risk/qsra/runs").json()) == 1


def test_register_rejects_an_unordered_impact_range(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    bad = client.post(f"/projects/{project.id}/risks", json={
        "title": "x", "impact_min": 10, "impact_ml": 5, "impact_max": 20,
    })
    assert bad.status_code == 422


def test_closed_and_already_scheduled_risks_stay_out(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id)
    for body in (
        {"title": "closed", "status": "closed"},
        {"title": "in p6", "impact_in_schedule": True},
    ):
        client.post(f"/projects/{project.id}/risks", json={
            **body, "qsra_enabled": True, "probability_pct": 90, "impact_ml": 50, "impact_max": 60,
            "activity_external_ids": ["A300"],
        })
    res = client.post(f"/projects/{project.id}/risk/qsra/runs").json()["results"]
    assert res["drivers"] == []
    assert [n["reason"] for n in res["model_check"]["no_effect"]] == ["Impact already in the P6 schedule"]


def test_settings_round_trip_and_target_probability(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id)
    s = client.put(f"/projects/{project.id}/risk/qsra/settings", json={"confidence": "low", "target_date": "2030-01-01"})
    assert s.status_code == 200 and s.json()["confidence"] == "low"
    res = client.post(f"/projects/{project.id}/risk/qsra/runs").json()["results"]
    assert res["target_date"] == "2030-01-01"
    assert res["pre"]["prob_meet_target"] == 100.0


def test_early_warnings_resources_and_recommendations_respond(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, "resource_loaded_project.xer")

    ew = client.get(f"/projects/{project.id}/risk/early-warnings")
    assert ew.status_code == 200, ew.text
    ids = {i["id"] for i in ew.json()["indicators"]}
    assert {"slip", "margin", "bei", "stuck", "density", "confidence"} <= ids

    rs = client.get(f"/projects/{project.id}/risk/resources")
    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["total"]["budget"] > 0
    assert body["total"]["method"] == "insufficient"  # one update: no production history yet
    assert body["per_resource"]

    rec = client.get(f"/projects/{project.id}/risk/recommendations")
    assert rec.status_code == 200 and "items" in rec.json()


def test_assignments_snapshot_is_captured_on_import(client, db_session):
    from app.models.schedule_import import ScheduleImport

    tenant, project = _setup(db_session)
    _login(client)
    imp = _upload(client, project.id, "resource_loaded_project.xer")
    db_session.expire_all()
    row = db_session.get(ScheduleImport, __import__("uuid").UUID(imp["id"]))
    assert row.assignments_snapshot and {"external_id", "rsrc_id", "budget", "actual", "remaining"} <= set(
        row.assignments_snapshot[0]
    )


def test_subcontractors_cannot_see_risk_analysis(client, db_session):
    from app.models.user_tenant_role import TenantRole
    from tests.factories import add_membership, create_user

    tenant, project = _setup(db_session)
    sub = create_user(db_session, "sub-qsra@example.com", "secret123")
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    client.post("/auth/login", json={"email": "sub-qsra@example.com", "password": "secret123"})
    assert client.get(f"/projects/{project.id}/risk/early-warnings").status_code == 403


_ = Activity  # imported for the fixture's model registration side effects
