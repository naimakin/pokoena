"""Activity Criticality Score (services/criticality.py)."""

from datetime import date
from types import SimpleNamespace

from app.models.activity import ActivityStatus
from app.services.criticality import (
    criticality,
    duration_score,
    free_float_score,
    site_risk_score,
    total_float_score,
)
from tests.test_progress_roundtrip import SYNTHETIC, _activity, _login, _upload
from tests.test_schedule_import import _setup


def _act(**kw):
    """An activity on an 8h/day calendar, not started, spanning 10 days."""
    base = dict(
        status=ActivityStatus.not_started,
        task_type="TT_Task",
        hours_per_day=8.0,
        total_float_hours=0.0,
        free_float_hours=0.0,
        target_duration_hours=80.0,
        early_start=date(2026, 3, 1),
        early_finish=date(2026, 3, 10),
        planned_start=None,
        planned_finish=None,
        actual_start=None,
        actual_finish=None,
        site_risk=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_scoring_table():
    assert [total_float_score(d) for d in (-2, 0, 1, 5, 6, 15, 16)] == [100, 100, 80, 80, 50, 50, 20]
    assert [duration_score(s) for s in (0.2, 0.10, 0.05, 0.049)] == [100, 70, 70, 30]
    assert [free_float_score(0, n) for n in (3, 2, 1, 0)] == [100, 70, 70, 20]
    assert free_float_score(16, 5) == 20
    assert [site_risk_score(r) for r in ("high", "standard", "low", None)] == [100, 50, 10, 50]


def test_worked_examples():
    # B — facade panels: TF 8d, long (> 10% of the project), FF 0 with three
    # successors, imported / high risk -> 50*.4 + 100*.2 + 100*.2 + 100*.2 = 80.
    b = _act(total_float_hours=64.0, site_risk="high")
    assert criticality(b, project_days=50, successor_count=3).score == 80
    # C — interior paint: TF 25d, short, FF > 0, low risk
    # -> 20*.4 + 30*.2 + 20*.2 + 10*.2 = 20.
    c = _act(total_float_hours=200.0, free_float_hours=80.0, site_risk="low")
    result = criticality(c, project_days=500, successor_count=1)
    assert result.score == 20
    assert result.breakdown == {"total_float": 20, "duration": 30, "free_float": 20, "site_risk": 10}


def test_float_is_in_the_activitys_own_calendar_days():
    # 60h is 6d on a 10h calendar (-> 50) but 7.5d on 8h — both > 5d; 50h is
    # 5d on 10h (-> 80) but 6.25d on 8h (-> 50).
    assert criticality(_act(total_float_hours=50.0, hours_per_day=10.0), 100, 0).breakdown["total_float"] == 80
    assert criticality(_act(total_float_hours=50.0, hours_per_day=8.0), 100, 0).breakdown["total_float"] == 50


def test_no_score_for_finished_or_unscheduled_work():
    assert criticality(_act(status=ActivityStatus.complete), 100, 3) is None
    assert criticality(_act(total_float_hours=None), 100, 3) is None


def test_milestone_has_no_duration_weight():
    ms = _act(task_type="TT_FinMile", target_duration_hours=0.0)
    assert criticality(ms, 10, 0).breakdown["duration"] == 30


def test_activities_carry_a_score_and_site_risk_moves_it(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, SYNTHETIC.read_bytes())

    rows = {a["external_id"]: a for a in client.get(f"/activities?project_id={project.id}").json()}
    a200 = rows["A200"]
    assert a200["criticality_score"] is not None
    assert a200["criticality_breakdown"]["site_risk"] == 50  # not assessed = standard

    a200_row = _activity(db_session, project.id, "A200")
    body = client.patch(f"/activities/{a200_row.id}", json={"site_risk": "high"}).json()
    assert body["site_risk"] == "high"
    assert body["criticality_breakdown"]["site_risk"] == 100
    assert body["criticality_score"] == a200["criticality_score"] + 10

    assert client.patch(f"/activities/{a200_row.id}", json={"site_risk": "extreme"}).status_code == 422
