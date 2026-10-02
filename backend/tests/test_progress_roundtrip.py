"""Progress between P6 and Poko, both ways.

- A P6 export that carries baselines alongside the programme reads only the
  programme (the baselines share its task_codes).
- An update import brings P6's progress in unless Poko is already ahead.
- Progress entered in Poko zeroes a finished activity's float and splits its
  LABOR resource units by % (material / equipment units don't follow it), and
  the .xer export writes the same into TASK and TASKRSRC.
"""

from pathlib import Path

from app.engine.export.xer_progress import decode_xer, rewrite_progress
from app.models.activity import Activity
from app.models.resource_assignment import ResourceAssignment
from app.parser.xer_parser import parse_xer
from tests.test_schedule_import import _setup

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic_project.xer"
RESOURCE_LOADED = FIXTURES / "resource_loaded_project.xer"


def _edit_rows(text: str, table: str, match: dict[str, str], values: dict[str, str]) -> str:
    """Set `values` on every row of `table` whose cells equal `match`."""
    out, current, cols = [], None, []
    for line in text.split("\n"):
        if line.startswith("%T\t"):
            current = line.split("\t")[1]
        elif line.startswith("%F\t"):
            cols = line.split("\t")[1:]
        elif line.startswith("%R\t") and current == table:
            cells = line.split("\t")[1:]
            if all(cells[cols.index(k)] == v for k, v in match.items()):
                for k, v in values.items():
                    cells[cols.index(k)] = v
                line = "%R\t" + "\t".join(cells)
        out.append(line)
    return "\n".join(out)


def _with_baseline_copy(text: str) -> str:
    """The file as P6 writes it when a baseline is exported alongside: an extra
    PROJECT row (export_flag N, orig_proj_id set) and a not-started copy of
    every task under the baseline's proj_id, with the SAME task_codes, written
    after the programme's own rows."""
    lines = text.split("\n")
    out = []
    table = None
    task_rows = []
    for line in lines:
        if line.startswith("%T\t"):
            if table == "TASK":
                for row in task_rows:
                    cells = row.split("\t")
                    cells[1] = str(int(cells[1]) + 1000)  # task_id
                    cells[2] = "BSL1"  # proj_id
                    cells[8] = "TK_NotStart"
                    cells[9] = "0"
                    out.append("\t".join(cells))
            table = line.split("\t")[1]
        elif table == "PROJECT" and line.startswith("%F\t"):
            line += "\texport_flag\torig_proj_id"
        elif table == "PROJECT" and line.startswith("%R\t"):
            out.append(line + "\tY\t")
            line = line.replace("PROJ1", "BSL1") + "\tN\tPROJ1"
        elif table == "TASK" and line.startswith("%R\t"):
            task_rows.append(line)
        out.append(line)
    return "\n".join(out)


def _a100_complete(text: str) -> str:
    text = _edit_rows(
        text,
        "TASK",
        {"task_code": "A100"},
        {
            "status_code": "TK_Complete",
            "phys_complete_pct": "100",
            "remain_drtn_hr_cnt": "0",
            "act_start_date": "2026-01-05 08:00",
            "act_end_date": "2026-01-05 17:00",
        },
    )
    return _edit_rows(text, "PROJECT", {"proj_id": "PROJ1"}, {"last_recalc_date": "2026-01-06 08:00"})


def _login(client):
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})


def _upload(client, project_id, content: bytes, name="upd.xer"):
    response = client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": (name, content, "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _activity(db_session, project_id, code) -> Activity:
    db_session.expire_all()
    return db_session.query(Activity).filter(Activity.project_id == project_id, Activity.external_id == code).one()


# --- reading P6 ---------------------------------------------------------------


def test_a_baseline_exported_alongside_is_not_read_as_the_programme():
    text = _with_baseline_copy(_a100_complete(SYNTHETIC.read_text("utf-8")))

    parsed = parse_xer(text.encode("utf-8"))

    assert parsed.meta.proj_id == "PROJ1"
    assert len(parsed.activities) == 6
    a100 = next(a for a in parsed.activities if a.task_code == "A100")
    assert a100.status_code == "TK_Complete"
    assert all(a.proj_id == "PROJ1" for a in parsed.activities)


def test_update_import_brings_in_progress_made_in_p6(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, SYNTHETIC.read_bytes(), "baseline.xer")
    assert _activity(db_session, project.id, "A100").status.value == "not_started"

    _upload(client, project.id, _a100_complete(SYNTHETIC.read_text("utf-8")).encode("utf-8"))

    a100 = _activity(db_session, project.id, "A100")
    assert a100.status.value == "complete"
    assert a100.percent_complete == 100
    assert a100.actual_start.isoformat() == "2026-01-05"
    assert a100.actual_finish.isoformat() == "2026-01-05"


def test_update_import_with_a_baseline_inside_still_brings_in_progress(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, SYNTHETIC.read_bytes(), "baseline.xer")

    text = _with_baseline_copy(_a100_complete(SYNTHETIC.read_text("utf-8")))
    body = _upload(client, project.id, text.encode("utf-8"))

    assert body["activity_count"] == 6
    assert _activity(db_session, project.id, "A100").status.value == "complete"


def test_update_import_keeps_poko_progress_that_is_ahead_of_the_file(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, SYNTHETIC.read_bytes(), "baseline.xer")
    a200 = _activity(db_session, project.id, "A200")
    assert client.patch(f"/activities/{a200.id}", json={"percent_complete": 60}).status_code == 200

    # The file moved A100 on, but knows nothing of A200's 60%.
    _upload(client, project.id, _a100_complete(SYNTHETIC.read_text("utf-8")).encode("utf-8"))

    assert _activity(db_session, project.id, "A100").status.value == "complete"
    assert _activity(db_session, project.id, "A200").percent_complete == 60


# --- progress entered in Poko ------------------------------------------------------


def _assignments(db_session, activity_id) -> dict[float, ResourceAssignment]:
    """By budgeted units — A200 carries two assignments: 40 (RT_Labor) and
    100 (RT_Material)."""
    db_session.expire_all()
    rows = db_session.query(ResourceAssignment).filter(ResourceAssignment.activity_id == activity_id).all()
    return {a.target_qty: a for a in rows}


def test_percent_complete_splits_resource_units(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, RESOURCE_LOADED.read_bytes())
    a200 = _activity(db_session, project.id, "A200")

    assert client.patch(f"/activities/{a200.id}", json={"percent_complete": 25}).status_code == 200

    by_budget = _assignments(db_session, a200.id)
    assert (by_budget[40].act_reg_qty, by_budget[40].remain_qty) == (10, 30)
    assert (by_budget[100].act_reg_qty, by_budget[100].remain_qty) == (0, 100)  # material
    assert by_budget[40].act_reg_cost == 0  # costs stay the AC side of EVM


def test_actual_finish_zeroes_float_and_burns_all_units(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, RESOURCE_LOADED.read_bytes())
    a200 = _activity(db_session, project.id, "A200")

    response = client.patch(
        f"/activities/{a200.id}", json={"actual_start": "2026-01-06", "actual_finish": "2026-01-12"}
    )

    assert response.status_code == 200
    body = response.json()
    # Finished work has no float — blank, as P6 writes it.
    assert body["total_float_hours"] is None
    assert body["free_float_hours"] is None
    assert body["is_critical"] is False
    by_budget = _assignments(db_session, a200.id)
    assert (by_budget[40].act_reg_qty, by_budget[40].remain_qty) == (40, 0)
    assert (by_budget[100].act_reg_qty, by_budget[100].remain_qty) == (0, 100)  # material


def test_batch_progress_edit_splits_units_too(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, RESOURCE_LOADED.read_bytes())
    a200 = _activity(db_session, project.id, "A200")

    response = client.patch(
        f"/activities?project_id={project.id}", json={"updates": [{"id": str(a200.id), "percent_complete": 50}]}
    )

    assert response.status_code == 200
    assert _assignments(db_session, a200.id)[40].act_reg_qty == 20


# --- writing P6 ---------------------------------------------------------------------


def _table(text: str, table: str) -> list[dict[str, str]]:
    rows, current, cols = [], None, []
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("%T\t"):
            current = line.split("\t")[1]
        elif line.startswith("%F\t"):
            cols = line.split("\t")[1:]
        elif line.startswith("%R\t") and current == table:
            rows.append(dict(zip(cols, line.split("\t")[1:])))
    return rows


def test_export_writes_units_dates_and_zero_float_into_task_and_taskrsrc(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, RESOURCE_LOADED.read_bytes())
    a200 = _activity(db_session, project.id, "A200")
    client.patch(f"/activities/{a200.id}", json={"actual_start": "2026-01-06", "actual_finish": "2026-01-12"})

    exported = client.get(f"/projects/{project.id}/export/xer")

    assert exported.status_code == 200
    text, _ = decode_xer(exported.content)
    task = next(r for r in _table(text, "TASK") if r["task_code"] == "A200")
    assert task["status_code"] == "TK_Complete"
    assert task["act_end_date"].startswith("2026-01-12")
    assert task["total_float_hr_cnt"] == ""
    assert task["free_float_hr_cnt"] == ""
    a200_assignments = {r["rsrc_id"]: r for r in _table(text, "TASKRSRC") if r["task_id"] == task["task_id"]}
    assert (a200_assignments["R1"]["act_reg_qty"], a200_assignments["R1"]["remain_qty"]) == ("40", "0")
    assert a200_assignments["R3"]["act_reg_qty"] == "0"  # RT_Material: units don't follow the %
    # An untouched activity's assignment passes through as P6 wrote it.
    untouched = next(r for r in _table(text, "TASKRSRC") if r["task_id"] != task["task_id"])
    assert untouched["act_reg_qty"] == "0"


def test_export_moves_the_assignment_dates_with_the_activity():
    source = "\n".join(
        [
            "%T\tPROJECT",
            "%F\tproj_id\texport_flag\torig_proj_id",
            "%R\tP1\tY\t",
            "%R\tB1\tN\tP1",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\tstatus_code\tphys_complete_pct\tact_start_date\tact_end_date"
            "\tremain_drtn_hr_cnt\ttotal_float_hr_cnt\tfree_float_hr_cnt\ttarget_work_qty\tact_work_qty\tremain_work_qty",
            "%R\t1\tP1\tK1\tTK_Active\t50\t2026-05-12 08:00\t\t8\t352\t0\t16\t8\t8",
            "%R\t2\tB1\tK1\tTK_NotStart\t0\t\t\t16\t0\t0\t16\t0\t16",
            "%T\tRSRC",
            "%F\trsrc_id\trsrc_type",
            "%R\tL1\tRT_Labor",
            "%T\tTASKRSRC",
            "%F\ttaskrsrc_id\ttask_id\trsrc_id\ttarget_qty\tact_reg_qty\tremain_qty\tact_start_date\tact_end_date"
            "\trestart_date\treend_date",
            "%R\t10\t1\tL1\t16\t8\t8\t2026-05-12 08:00\t\t2026-05-13 08:00\t2026-05-13 17:00",
            "%R\t20\t2\tL1\t16\t0\t16\t\t\t\t",
            "%E",
            "",
        ]
    )
    from datetime import date
    from types import SimpleNamespace

    from app.models.activity import ActivityStatus

    k1 = SimpleNamespace(
        external_id="K1",
        percent_complete=100,
        status=ActivityStatus.complete,
        actual_start=date(2026, 5, 12),
        actual_finish=date(2026, 5, 15),
        remaining_duration_hours=0,
        remaining_duration_days=0,
    )

    out, task_rows, updated = rewrite_progress(source.encode("utf-8"), [k1])
    text, _ = decode_xer(out)

    assert (task_rows, updated) == (1, 1)
    tasks = {r["proj_id"]: r for r in _table(text, "TASK")}
    assert tasks["P1"]["act_end_date"] == "2026-05-15 17:00"
    assert tasks["P1"]["total_float_hr_cnt"] == ""
    assert (tasks["P1"]["act_work_qty"], tasks["P1"]["remain_work_qty"]) == ("16", "0")
    # The baseline copy of K1 is left exactly as P6 wrote it.
    assert tasks["B1"]["status_code"] == "TK_NotStart"

    assignments = {r["task_id"]: r for r in _table(text, "TASKRSRC")}
    assert assignments["1"]["act_end_date"] == "2026-05-15 17:00"
    assert (assignments["1"]["act_reg_qty"], assignments["1"]["remain_qty"]) == ("16", "0")
    assert (assignments["1"]["restart_date"], assignments["1"]["reend_date"]) == ("", "")
    assert assignments["2"]["act_reg_qty"] == "0"
