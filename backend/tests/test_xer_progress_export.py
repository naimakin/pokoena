"""The .xer export carries Poko's progress back into P6.

Built as a patch of the original P6 file rather than a generated one — see
engine/export/xer_progress.py for why.
"""

from datetime import date
from types import SimpleNamespace

from app.engine.export.xer_progress import decode_xer, rewrite_progress
from app.models.activity import ActivityStatus

# Trimmed to the columns that matter, in P6's own order, with the surrounding
# tables a real export carries so the pass-through can be asserted.
SOURCE = "\n".join(
    [
        "ERMHDR\t22.12\t2023-10-20\tProject\tADMIN\tAli\tdbxDatabaseNoName\tProject Management\tEUR",
        "%T\tPROJECT",
        "%F\tproj_id\tproj_short_name\texport_flag",
        "%R\t396\tCPH07\tY",
        "%T\tPROJWBS",
        "%F\twbs_id\tproj_id\tproj_node_flag\twbs_name",
        "%R\t15701\t396\tY\tCPH07",
        "%T\tTASK",
        "%F\ttask_id\tproj_id\ttask_code\ttask_name\tphys_complete_pct\tstatus_code"
        "\tremain_drtn_hr_cnt\tact_start_date\tact_end_date\ttarget_drtn_hr_cnt",
        "%R\t80202\t396\tA1000\tKazı işleri\t0\tTK_NotStart\t40\t\t\t40",
        "%R\t80203\t396\tA1010\tGrobeton\t0\tTK_NotStart\t16\t\t\t16",
        "%R\t80204\t396\tA1020\tUntouched\t0\tTK_NotStart\t8\t\t\t8",
        "%T\tTASKPRED",
        "%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type",
        "%R\t1\t80203\t80202\tPR_FS",
        "%E",
        "",
    ]
)


def _activity(code, **kw):
    return SimpleNamespace(
        external_id=code,
        percent_complete=kw.get("percent_complete", 0),
        status=kw.get("status", ActivityStatus.not_started),
        actual_start=kw.get("actual_start"),
        actual_finish=kw.get("actual_finish"),
        remaining_duration_hours=kw.get("remaining_duration_hours"),
        remaining_duration_days=kw.get("remaining_duration_days", 0),
    )


def _task_rows(text: str) -> dict[str, list[str]]:
    rows, in_task = {}, False
    for line in text.split("\n"):
        if line.startswith("%T\t"):
            in_task = line.split("\t")[1] == "TASK"
        elif line.startswith("%R\t") and in_task:
            cells = line.split("\t")[1:]
            rows[cells[2]] = cells
    return rows


def _roundtrip(activities):
    out, task_rows, updated = rewrite_progress(SOURCE.encode("cp1254"), activities)
    text, _ = decode_xer(out)
    assert task_rows == 3
    return _task_rows(text), text, updated


def test_progress_is_written_into_the_task_row():
    rows, _text, updated = _roundtrip(
        [
            _activity(
                "A1000",
                percent_complete=100,
                status=ActivityStatus.complete,
                actual_start=date(2026, 3, 2),
                actual_finish=date(2026, 3, 6),
            )
        ]
    )

    assert updated == 1
    a1000 = rows["A1000"]
    assert a1000[4] == "100"  # phys_complete_pct
    assert a1000[5] == "TK_Complete"  # status_code
    assert a1000[6] == "0"  # remain_drtn_hr_cnt — complete work has none left
    assert a1000[7] == "2026-03-02 08:00"  # act_start_date, P6 datetime shape
    assert a1000[8] == "2026-03-06 17:00"  # act_end_date


def test_in_progress_activity_keeps_its_remaining_duration():
    rows, _text, _updated = _roundtrip(
        [
            _activity(
                "A1010",
                percent_complete=40,
                status=ActivityStatus.in_progress,
                actual_start=date(2026, 3, 9),
                remaining_duration_days=2,
            )
        ]
    )

    a1010 = rows["A1010"]
    assert a1010[4] == "40"
    assert a1010[5] == "TK_Active"
    assert a1010[6] == "16"  # 2 days x 8h
    assert a1010[7] == "2026-03-09 08:00"
    assert a1010[8] == ""  # no actual finish yet


def test_rows_with_no_matching_activity_and_other_tables_pass_through():
    rows, text, updated = _roundtrip([_activity("A1000", percent_complete=50, status=ActivityStatus.in_progress)])

    assert updated == 1
    assert rows["A1020"][4] == "0"
    assert rows["A1020"][5] == "TK_NotStart"
    # Everything P6 needs beyond TASK survives untouched.
    assert text.startswith("ERMHDR\t22.12\t")
    assert "%R\t15701\t396\tY\tCPH07" in text
    assert "%R\t1\t80203\t80202\tPR_FS" in text
    assert text.rstrip("\n").endswith("%E")


def test_non_ascii_names_survive_the_roundtrip():
    _rows, text, _updated = _roundtrip([_activity("A1000")])

    assert "Kazı işleri" in text


_UNTOUCHED_A1020 = "%R\t80204\t396\tA1020\tUntouched\t0\tTK_NotStart\t8\t\t\t8"
_FINISHED_A1020 = "%R\t80204\t396\tA1020\tUntouched\t100\tTK_Complete\t0\t2026-01-05 08:00\t2026-01-09 17:00\t8"


def test_an_activity_poko_agrees_with_is_left_exactly_as_p6_wrote_it():
    # Same status, dates, % and remaining as the row: nothing to write, so the
    # row goes back byte-for-byte (P6's own times, blanks and number format).
    source = SOURCE.replace(_UNTOUCHED_A1020, _FINISHED_A1020)
    finished = _activity(
        "A1020",
        percent_complete=100,
        status=ActivityStatus.complete,
        actual_start=date(2026, 1, 5),
        actual_finish=date(2026, 1, 9),
        remaining_duration_hours=0,
    )
    out, task_rows, updated = rewrite_progress(source.encode("cp1254"), [finished])

    assert task_rows == 3
    assert updated == 0
    assert out == source.encode("cp1254")


def test_an_undo_in_poko_reaches_p6():
    # The row says Complete, Poko put the activity back to Not Started: the
    # row has to follow, or P6 keeps the progress the user took back.
    source = SOURCE.replace(_UNTOUCHED_A1020, _FINISHED_A1020)
    out, _count, updated = rewrite_progress(
        source.encode("cp1254"), [_activity("A1020", remaining_duration_hours=8)]
    )
    text, _ = decode_xer(out)

    assert updated == 1
    a1020 = _task_rows(text)["A1020"]
    assert (a1020[4], a1020[5], a1020[6], a1020[7], a1020[8]) == ("0", "TK_NotStart", "8", "", "")


def test_crlf_line_endings_are_preserved():
    # A real P6 export is CRLF throughout. Rewriting it as LF changes every
    # line in the file when only a handful of cells were meant to move.
    source = SOURCE.replace("\n", "\r\n").encode("cp1254")
    out, _count, _updated = rewrite_progress(
        source, [_activity("A1000", percent_complete=25, status=ActivityStatus.in_progress)]
    )

    assert out.count(b"\r\n") == source.count(b"\r\n")
    assert b"\n" not in out.replace(b"\r\n", b"")


def test_existing_time_of_day_is_preserved():
    source = SOURCE.replace(
        "%R\t80202\t396\tA1000\tKazı işleri\t0\tTK_NotStart\t40\t\t\t40",
        "%R\t80202\t396\tA1000\tKazı işleri\t0\tTK_NotStart\t40\t2026-03-02 06:30\t\t40",
    )
    out, _count, _updated = rewrite_progress(
        source.encode("cp1254"),
        [_activity("A1000", status=ActivityStatus.in_progress, actual_start=date(2026, 3, 3))],
    )
    text, _ = decode_xer(out)

    assert _task_rows(text)["A1000"][7] == "2026-03-03 06:30"


def test_quantities_keep_their_precision():
    # `:g` kept 6 significant digits: 22255.74 x 40% went out as 8902.3 +
    # 13353.4, which no longer adds up to the budget P6 holds.
    from app.engine.export.xer_progress import _num

    assert _num(8902.296) == "8902.296"
    assert _num(12613.637582) == "12613.637582"
    assert _num(40.0) == "40"
    assert _num(0.0) == "0"
    assert _num(-0.0000001) == "0"
