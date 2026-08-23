from datetime import datetime, timedelta

from app.parser.xer_parser import _parse_clndr_data

# A real production import crashed on this exact format — the reference
# desktop app's own parser never handled it either (same flat-token
# assumption we started with), so this is the first time either codebase
# has correctly parsed a real P6 clndr_data field. See
# app/parser/xer_parser.py's "modern nested variant" section for the grammar.
_NESTED_SAMPLE = (
    "(0||CalendarData()("
    "  (0||DaysOfWeek()("
    "    (0||1()("
    "      (0||0(s|08:00|f|12:00)())"
    "      (0||1(s|13:00|f|17:00)())))"
    "    (0||2()("
    "      (0||0(s|08:00|f|17:00)())))"
    "    (0||3()())"
    "    (0||4()("
    "      (0||0(s|08:00|f|17:00)())))"
    "    (0||5()("
    "      (0||0(s|08:00|f|17:00)())))"
    "    (0||6()("
    "      (0||0(s|08:00|f|17:00)())))"
    "    (0||7()())))"
    "  (0||VIEW(ShowTotal|N)())"
    "  (0||Exceptions()("
    "    (0||0(d|43831)())"
    "    (0||1(d|44197)("
    "      (0||0(s|09:00|f|13:00)())))))))"
)


def test_nested_clndr_data_maps_days_of_week_correctly():
    """Nested format day numbering is 1=Sun...7=Sat (P6's VB-style
    convention) — must map onto this app's 0=Sun...6=Sat CalendarDay.day_of_week."""
    week, _ = _parse_clndr_data("CAL1", _NESTED_SAMPLE, [])
    by_dow = {d.day_of_week: d for d in week}

    assert len(week) == 7
    assert by_dow[0].is_working and len(by_dow[0].shifts) == 2  # Sun: two shifts
    assert by_dow[0].shifts[0].start.hour == 8 and by_dow[0].shifts[1].end.hour == 17
    assert by_dow[1].is_working and len(by_dow[1].shifts) == 1  # Mon
    assert not by_dow[2].is_working  # Tue: day off (empty children)
    assert by_dow[3].is_working  # Wed
    assert by_dow[4].is_working  # Thu
    assert by_dow[5].is_working  # Fri
    assert not by_dow[6].is_working  # Sat: day off


def test_nested_clndr_data_exceptions_use_the_p6_serial_date_epoch():
    """Exception dates are a day count from 1899-12-30 (OLE Automation /
    Delphi TDateTime epoch — P6's desktop client is Delphi-based)."""
    _, exceptions = _parse_clndr_data("CAL1", _NESTED_SAMPLE, [])

    assert len(exceptions) == 2
    epoch = datetime(1899, 12, 30)

    full_day_off = exceptions[0]
    assert full_day_off.exc_date == epoch + timedelta(days=43831)
    assert not full_day_off.is_working

    partial_day = exceptions[1]
    assert partial_day.exc_date == epoch + timedelta(days=44197)
    assert partial_day.is_working
    assert partial_day.shifts[0].start.hour == 9 and partial_day.shifts[0].end.hour == 13


def test_nested_clndr_data_tolerates_stray_control_bytes():
    """A real production import kept crashing after the nested-format fix
    shipped: this exact real export prefixes clndr_data with a couple of
    \\x7f (DEL) bytes before the "(0||" marker, and scatters more between
    sibling nodes. str.strip() doesn't remove control characters, so a plain
    startswith("(0||") dispatch check silently fell back to the legacy
    parser and re-produced the original "no working day" crash. The
    dispatcher now searches for the marker instead of anchoring to index 0,
    and the node parser already skips any non-'(' filler between children."""
    noisy = "\x7f\x7f" + _NESTED_SAMPLE.replace("(0||VIEW", "\x7f\x7f(0||VIEW")
    week, exceptions = _parse_clndr_data("CAL1", noisy, [])

    by_dow = {d.day_of_week: d for d in week}
    assert by_dow[0].is_working and len(by_dow[0].shifts) == 2
    assert not by_dow[2].is_working
    assert len(exceptions) == 2


def test_legacy_flat_clndr_data_still_parses():
    """The older `(dow|HH:MM|HH:MM)` flat format (this project's own synthetic
    test fixture) must keep working — real exports can use either variant."""
    legacy = "(0)(1|08:00|17:00)(2|08:00|17:00)(3|08:00|17:00)(4|08:00|17:00)(5|08:00|17:00)(6)"
    week, exceptions = _parse_clndr_data("CAL1", legacy, [])

    by_dow = {d.day_of_week: d for d in week}
    assert not by_dow[0].is_working  # Sun
    assert by_dow[1].is_working and by_dow[1].shifts[0].start.hour == 8  # Mon
    assert not by_dow[6].is_working  # Sat
    assert exceptions == []


def test_calendar_with_no_working_days_produces_all_non_working_days():
    """A genuinely blank calendar (every day present but with no shifts) must
    still parse cleanly to seven non-working CalendarDays — the caller (CPM
    scheduler) is what turns that into a user-facing error, not the parser."""
    blank = "(0||CalendarData()((0||DaysOfWeek()(" + "".join(f"(0||{d}()())" for d in range(1, 8)) + "))))"
    week, _ = _parse_clndr_data("CAL1", blank, [])

    assert len(week) == 7
    assert all(not d.is_working for d in week)
