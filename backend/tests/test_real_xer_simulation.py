"""Schedule Simulation on REAL P6 exports — the acceptance check the synthetic
fixture can't give (thousands of activities, several calendars, constraints,
out-of-sequence progress). Skipped unless POKO_REAL_XER names .xer files
(os.pathsep-separated); run with -s for the report:

    POKO_REAL_XER="C:/path/a.xer;C:/path/b.xer" pytest tests/test_real_xer_simulation.py -s

Per file: import it, then simulate (1) the longest-path activity finishing 15
working days later, (2) the most negative-float unstarted activity marked
complete, (3) the data date two weeks on with no change. Every activity that
moves because of a change must trace back to it (a `cause` chain ending at
the changed activity); a delay can't move the finish by more than itself.
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

PATHS = [p for p in os.environ.get("POKO_REAL_XER", "").split(os.pathsep) if p.strip()]

pytestmark = pytest.mark.skipif(not PATHS, reason="POKO_REAL_XER not set")


def _chain_ok(rows: dict, row: dict, edited: set[str]) -> bool:
    seen = set()
    while row is not None and row["external_id"] not in seen:
        if row["external_id"] in edited:
            return True
        seen.add(row["external_id"])
        cause = row["cause"]
        row = rows.get(cause["external_id"]) if cause else None
    return False


@pytest.mark.parametrize("path", PATHS, ids=[Path(p).stem for p in PATHS])
def test_simulation_on_real_programme(client, db_session, path):
    tenant = create_tenant(db_session, name="Real", slug="real-sim")
    admin = create_user(db_session, "real-sim@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    project = create_project(db_session, tenant, name="Real", code="REAL")
    client.post("/auth/login", json={"email": "real-sim@example.com", "password": "secret123"})
    raw = Path(path).read_bytes()
    r = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": (Path(path).name, raw, "application/octet-stream")},
        data={"force": "true"},
    )
    assert r.status_code == 201, r.text

    ctx = client.get(f"/projects/{project.id}/simulations/context").json()
    acts = ctx["activities"]
    print(f"\n== {Path(path).name}: {len(acts)} activities, data date {ctx['current_data_date']}")

    def run(edits, data_date=None):
        t = time.perf_counter()
        body = {"edits": edits} | ({"data_date": data_date} if data_date else {})
        resp = client.post(f"/projects/{project.id}/simulations/run", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json(), time.perf_counter() - t

    base, secs = run([])
    assert base["moved"] == [], "an unchanged run must move nothing"
    print(f"   unchanged: finish {base['project_finish']['simulated']}  ({secs:.2f}s)")

    open_tasks = [a for a in acts if a["status"] != "complete" and not a["is_milestone"]]
    critical = sorted(
        (a for a in open_tasks if a["total_float_days"] is not None),
        key=lambda a: (a["total_float_days"], a["finish"] or ""),
    )
    if critical:
        target = critical[0]["external_id"]
        delayed, secs = run([{"external_id": target, "kind": "finish_delay", "value": 15}])
        rows = {r["external_id"]: r for r in delayed["moved"]}
        unexplained = [
            r["external_id"] for r in delayed["moved"] if r["direction"] == "later" and not _chain_ok(rows, r, {target})
        ]
        print(
            f"   {target} +15d: {delayed['counts']['later']} later, finish {delayed['project_finish']['unchanged']} -> "
            f"{delayed['project_finish']['simulated']} ({delayed['project_finish']['delta_days']:+}d), "
            f"{delayed['counts']['milestones_moved']} milestones, unexplained {len(unexplained)}  ({secs:.2f}s)"
        )
        assert not unexplained, unexplained[:10]
        assert delayed["project_finish"]["delta_days"] <= 15.01

    unstarted = [a for a in open_tasks if a["status"] == "not_started" and a["total_float_days"] is not None]
    if unstarted:
        worst = min(unstarted, key=lambda a: a["total_float_days"])["external_id"]
        done, secs = run([{"external_id": worst, "kind": "complete"}])
        rows = {r["external_id"]: r for r in done["moved"]}
        unexplained = [
            r["external_id"] for r in done["moved"] if r["direction"] == "earlier" and not _chain_ok(rows, r, {worst})
        ]
        print(
            f"   {worst} complete: {done['counts']['earlier']} earlier, finish "
            f"{done['project_finish']['delta_days']:+}d, unexplained {len(unexplained)}  ({secs:.2f}s)"
        )
        assert not unexplained, unexplained[:10]
        assert done["project_finish"]["delta_days"] <= 0.01

    later_dd = (date.fromisoformat(ctx["current_data_date"]) + timedelta(days=14)).isoformat()
    moved_dd, secs = run([], data_date=later_dd)
    assert moved_dd["moved"] == []
    print(
        f"   data date +14d, no change: {moved_dd['counts']['data_date_moved']} activities move, finish "
        f"{moved_dd['project_finish']['data_date_delta_days']:+}d  ({secs:.2f}s)"
    )
