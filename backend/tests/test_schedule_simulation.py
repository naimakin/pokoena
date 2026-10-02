"""Schedule Simulation (services/schedule_simulation.py, routes/simulations.py).

synthetic_project.xer: data date 05-Jan-2026 08:00, one 9h calendar (08:00-17:00,
Mon-Fri), A100 (1d) -> A200 (40h) -> A300 (24h) -> A600 (finish milestone)
and A100 -> A400 (8h) -> A500 (16h) -> A600. Unchanged, A600 lands on
14-Jan-2026; A400/A500 carry 40h (4.44d) of float.
"""

import uuid
from pathlib import Path

from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.project_membership import ProjectMembership
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURES = Path(__file__).parent / "fixtures"


def _setup(client, db_session, fixture="synthetic_project.xer"):
    tenant = create_tenant(db_session, name="Acme", slug="acme-sim")
    admin = create_user(db_session, "sim-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    project = create_project(db_session, tenant, name="Alpha", code="ALP")
    client.post("/auth/login", json={"email": "sim-admin@example.com", "password": "secret123"})
    r = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": (fixture, (FIXTURES / fixture).read_bytes(), "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    return tenant, project


def _run(client, project, edits=(), data_date=None, status=200):
    body = {"edits": list(edits)}
    if data_date:
        body["data_date"] = data_date
    r = client.post(f"/projects/{project.id}/simulations/run", json=body)
    assert r.status_code == status, r.text
    return r.json()


def _by_id(result):
    return {row["external_id"]: row for row in result["moved"]}


def test_no_changes_moves_nothing(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(client, project)

    assert result["moved"] == []
    assert result["current_data_date"] == result["simulation_data_date"] == "2026-01-05"
    finish = result["project_finish"]
    assert finish["simulated"] == finish["unchanged"] == finish["current"] == "2026-01-14"
    assert finish["delta_days"] == 0
    assert finish["external_id"] == "A600"


def test_finish_delay_moves_its_chain_and_says_why(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(client, project, [{"external_id": "A200", "kind": "finish_delay", "value": 2}])

    rows = _by_id(result)
    assert {k for k, r in rows.items() if r["direction"] == "later"} == {"A200", "A300", "A600"}
    assert rows["A600"]["finish_after"] == "2026-01-16"
    assert rows["A600"]["finish_delta_days"] == 2.0
    assert result["project_finish"]["delta_days"] == 2.0
    assert rows["A200"]["is_edited"] and rows["A200"]["driver"] == {"kind": "edit", "summary": "Finish moved by +2d"}
    assert rows["A300"]["driver"]["kind"] == "predecessor"
    assert rows["A300"]["driver"]["external_id"] == "A200" and rows["A300"]["driver"]["link_type"] == "FS"
    # The chain back to the change: A600 <- A300 <- A200.
    assert rows["A600"]["cause"]["external_id"] == "A300"
    assert rows["A300"]["cause"]["external_id"] == "A200"
    assert rows["A200"]["cause"] is None
    # The parallel path only gained float (4.44d -> 6.44d); its dates didn't move.
    assert "A400" not in rows and "A500" not in rows
    milestone = next(m for m in result["milestones"] if m["external_id"] == "A600")
    assert milestone["is_project_finish"] and milestone["direction"] == "later"


def test_delay_absorbed_by_float_leaves_the_finish(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(client, project, [{"external_id": "A400", "kind": "finish_delay", "value": 2}])

    rows = _by_id(result)
    assert {k for k, r in rows.items() if r["direction"] == "later"} == {"A400", "A500"}
    assert result["project_finish"]["delta_days"] == 0
    assert rows["A500"]["total_float_before_days"] > rows["A500"]["total_float_after_days"] > 0


def test_a_longer_delay_takes_over_the_critical_path(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(client, project, [{"external_id": "A400", "kind": "finish_delay", "value": 6}])

    rows = _by_id(result)
    assert rows["A600"]["direction"] == "later"
    assert rows["A600"]["driver"]["external_id"] == "A500"  # now driven by the other branch
    assert rows["A600"]["cause"]["external_id"] == "A500"
    assert 1.5 < result["project_finish"]["delta_days"] < 1.6  # 14h of a 9h day
    # A200/A300 left the critical path; A400/A500 joined it.
    assert not rows["A300"]["critical_after"] and rows["A300"]["critical_before"]
    assert rows["A500"]["critical_after"] and not rows["A500"]["critical_before"]
    assert result["counts"]["joined_critical"] >= 2 and result["counts"]["left_critical"] >= 2


def test_moving_the_data_date_is_reported_separately(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(client, project, data_date="2026-01-06")

    assert result["moved"] == []  # no changes, so nothing moved because of one
    assert result["project_finish"]["data_date_delta_days"] == 1.0
    assert result["project_finish"]["delta_days"] == 0
    assert result["counts"]["data_date_moved"] == 6


def test_marking_complete_pulls_the_programme_in(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(client, project, [{"external_id": "A100", "kind": "complete"}], data_date="2026-01-06")

    rows = _by_id(result)
    assert rows["A100"]["status_after"] == "complete" and rows["A100"]["finish_after"] == "2026-01-06"
    assert rows["A100"]["driver"] == {"kind": "edit", "summary": "Marked complete on 06-Jan-2026"}
    for code in ("A200", "A300", "A400", "A500", "A600"):
        assert rows[code]["direction"] == "earlier", code
    # Released by the change: A200's chain starts at A100.
    assert rows["A200"]["cause"]["external_id"] == "A100"
    assert result["project_finish"]["delta_days"] < 0


def test_out_of_sequence_progress_waits_for_its_predecessor(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(
        client, project, [{"external_id": "A200", "kind": "percent_complete", "value": 50}], data_date="2026-01-06"
    )

    rows = _by_id(result)
    assert rows["A200"]["status_after"] == "in_progress"
    # Retained Logic: the remaining 20h wait for A100 (which finishes 06-Jan 17:00).
    assert rows["A200"]["finish_after"] == "2026-01-09"
    assert any(w["code"] == "out_of_sequence" and w["external_id"] == "A200" for w in result["warnings"])
    assert result["project_finish"]["delta_days"] < 0


def test_finish_on_date_sizes_the_remaining_work(client, db_session):
    _, project = _setup(client, db_session)

    result = _run(client, project, [{"external_id": "A300", "kind": "finish_on", "value": "2026-01-20"}])

    rows = _by_id(result)
    assert rows["A300"]["finish_after"] == "2026-01-20"
    assert rows["A600"]["finish_after"] == "2026-01-20"


def test_milestone_takes_one_date(client, db_session):
    _, project = _setup(client, db_session)

    moved = _run(client, project, [{"external_id": "A600", "kind": "finish_on", "value": "2026-01-21"}])
    assert _by_id(moved)["A600"]["finish_after"] == "2026-01-21"

    bad = _run(client, project, [{"external_id": "A600", "kind": "percent_complete", "value": 50}], status=422)
    assert bad["detail"]["code"] == "invalid_edits"
    assert bad["detail"]["errors"][0]["external_id"] == "A600"


def test_invalid_changes_are_rejected_per_activity(client, db_session):
    _, project = _setup(client, db_session)

    cases = [
        [{"external_id": "A100", "kind": "complete", "value": "2026-01-09"}],  # after the simulation data date
        [{"external_id": "NOPE", "kind": "finish_delay", "value": 1}],
        [{"external_id": "A100", "kind": "finish_delay", "value": 1}, {"external_id": "A100", "kind": "finish_delay", "value": 2}],
        [{"external_id": "A200", "kind": "percent_complete", "value": 120}],
    ]
    for edits in cases:
        body = _run(client, project, edits, status=422)
        assert body["detail"]["code"] == "invalid_edits", edits

    before = _run(client, project, data_date="2026-01-02", status=422)
    assert before["detail"]["code"] == "data_date_before_current"


def test_runs_never_touch_the_live_schedule(client, db_session):
    _, project = _setup(client, db_session)
    snapshot = lambda: sorted(  # noqa: E731
        (a.external_id, a.status, a.early_finish, a.remaining_duration_hours, a.actual_finish)
        for a in db_session.query(Activity).filter(Activity.project_id == project.id)
    )
    before = snapshot()

    first = _run(client, project, [{"external_id": "A100", "kind": "complete"}, {"external_id": "A300", "kind": "finish_delay", "value": 3}], data_date="2026-01-07")
    second = _run(client, project, [{"external_id": "A100", "kind": "complete"}, {"external_id": "A300", "kind": "finish_delay", "value": 3}], data_date="2026-01-07")

    db_session.expire_all()
    assert snapshot() == before
    first.pop("run_at"), second.pop("run_at")
    assert first == second  # deterministic


def test_a_logic_loop_is_a_clear_error(client, db_session):
    tenant, project = _setup(client, db_session)
    acts = {a.external_id: a for a in db_session.query(Activity).filter(Activity.project_id == project.id)}
    db_session.add(
        ActivityRelationship(
            id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id,
            predecessor_id=acts["A600"].id, successor_id=acts["A100"].id, link_type=LinkType.FS, lag_days=0,
        )
    )
    db_session.commit()

    body = _run(client, project, status=422)
    assert body["detail"]["code"] == "logic_cycle"


def test_context_lists_the_programme(client, db_session):
    _, project = _setup(client, db_session)

    ctx = client.get(f"/projects/{project.id}/simulations/context").json()

    assert ctx["has_schedule"] and ctx["current_data_date"] == "2026-01-05"
    by = {a["external_id"]: a for a in ctx["activities"]}
    assert set(by) == {"A100", "A200", "A300", "A400", "A500", "A600"}
    assert by["A600"]["is_milestone"] and by["A600"]["start"] is None


def test_scenarios_save_and_permissions(client, db_session):
    tenant, project = _setup(client, db_session)
    edits = [{"external_id": "A200", "kind": "finish_delay", "value": 2}]

    created = client.post(
        f"/projects/{project.id}/simulations/scenarios",
        json={"name": "Foundation 2d late", "simulation_data_date": "2026-01-05", "edits": edits},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    assert created.json()["is_owner"] and created.json()["edits"][0]["external_id"] == "A200"

    run = _run(client, project, edits) | {}
    client.post(f"/projects/{project.id}/simulations/run", json={"edits": edits, "scenario_id": sid})
    listed = client.get(f"/projects/{project.id}/simulations/scenarios").json()
    assert listed[0]["last_finish_delta_days"] == run["project_finish"]["delta_days"] == 2.0
    assert listed[0]["stale"] is False

    renamed = client.patch(f"/projects/{project.id}/simulations/scenarios/{sid}", json={"name": "Renamed"})
    assert renamed.json()["name"] == "Renamed"

    # A member without an edit role can run and read, not save or delete.
    viewer = create_user(db_session, "sim-viewer@example.com", "secret123")
    add_membership(db_session, viewer, tenant, TenantRole.company_employee)
    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=viewer.id))
    sub = create_user(db_session, "sim-sub@example.com", "secret123")
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    db_session.commit()

    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "sim-viewer@example.com", "password": "secret123"})
    assert client.post(f"/projects/{project.id}/simulations/run", json={"edits": edits}).status_code == 200
    assert [s["name"] for s in client.get(f"/projects/{project.id}/simulations/scenarios").json()] == ["Renamed"]
    assert client.post(f"/projects/{project.id}/simulations/scenarios", json={"name": "x"}).status_code == 403
    assert client.delete(f"/projects/{project.id}/simulations/scenarios/{sid}").status_code == 403

    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "sim-sub@example.com", "password": "secret123"})
    assert client.post(f"/projects/{project.id}/simulations/run", json={"edits": edits}).status_code == 403
    assert client.get(f"/projects/{project.id}/simulations/scenarios").status_code == 403

    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "sim-admin@example.com", "password": "secret123"})
    assert client.delete(f"/projects/{project.id}/simulations/scenarios/{sid}").status_code == 204
    assert client.get(f"/projects/{project.id}/simulations/scenarios").json() == []


def test_another_tenant_cannot_reach_a_scenario(client, db_session):
    _, project = _setup(client, db_session)
    sid = client.post(f"/projects/{project.id}/simulations/scenarios", json={"name": "Mine"}).json()["id"]

    other = create_tenant(db_session, name="Other", slug="other-sim")
    outsider = create_user(db_session, "sim-out@example.com", "secret123")
    add_membership(db_session, outsider, other, TenantRole.company_admin)
    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "sim-out@example.com", "password": "secret123"})

    assert client.get(f"/projects/{project.id}/simulations/scenarios").status_code in (403, 404)
    assert client.delete(f"/projects/{project.id}/simulations/scenarios/{sid}").status_code in (403, 404)
