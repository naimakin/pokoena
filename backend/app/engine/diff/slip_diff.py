"""Slip diff between two schedule-import activity snapshots — "which activities'
finish moved later between the previous UPD and the latest one".

Pure functions over the `activities_snapshot` JSON blobs frozen on ScheduleImport
by services/xer_import.py (same "diff two frozen import snapshots" shape as
engine/diff/logic_diff.py). Deliberately independent of engine/evm/variance_engine
(that one is baseline-coupled and takes ORM rows) — but the "current finish"
definition below is copied verbatim from it and the two MUST stay identical, so
the Baseline Variance page and the Recovery Plan page never disagree about one
activity's finish date.
"""

from __future__ import annotations

from datetime import date


def _parse(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _finish(snap: dict) -> date | None:
    """actual_finish or planned_finish or early_finish — identical precedence to
    variance_engine.compute_baseline_date_variance's `current_finish`."""
    return _parse(snap.get("actual_finish")) or _parse(snap.get("planned_finish")) or _parse(
        snap.get("early_finish")
    )


def _day_diff(later: date | None, earlier: date | None) -> int | None:
    if later is None or earlier is None:
        return None
    return (later - earlier).days


def compute_slip_between_snapshots(
    prev: list[dict],
    curr: list[dict],
    *,
    threshold_days: int = 1,
) -> dict:
    """`prev` / `curr` are activities_snapshot lists (from ScheduleImport).
    Returns `{slipped, added, removed, summary}`.

    An activity has "slipped" when its finish moved later by more than
    `threshold_days` — except a critical / longest-path activity is surfaced on
    any positive slip (a 1-day slip on a zero-float activity is real)."""
    prev_by_extid = {a["external_id"]: a for a in prev}
    curr_by_extid = {a["external_id"]: a for a in curr}
    prev_by_p6 = {a["p6_task_id"]: a for a in prev if a.get("p6_task_id")}

    slipped: list[dict] = []
    added: list[dict] = []
    matched_prev_extids: set[str] = set()

    for c in curr:
        p = prev_by_extid.get(c["external_id"])
        if p is None and c.get("p6_task_id"):
            # Same rename guard as xer_import.py: match by P6 task_id only when
            # the old code truly went away.
            candidate = prev_by_p6.get(c["p6_task_id"])
            if candidate is not None and candidate["external_id"] not in curr_by_extid:
                p = candidate
        if p is None:
            added.append({"external_id": c["external_id"], "name": c.get("name")})
            continue

        matched_prev_extids.add(p["external_id"])
        prev_finish = _finish(p)
        curr_finish = _finish(c)
        slip_days = _day_diff(curr_finish, prev_finish)
        if slip_days is None or slip_days <= 0:
            continue
        is_critical = bool(c.get("is_critical")) or bool(c.get("is_longest_path"))
        if slip_days <= threshold_days and not is_critical:
            continue

        slipped.append(
            {
                "external_id": c["external_id"],
                "p6_task_id": c.get("p6_task_id"),
                "name": c.get("name"),
                "wbs_path": c.get("wbs_path"),
                "prev_finish": prev_finish.isoformat() if prev_finish else None,
                "curr_finish": curr_finish.isoformat() if curr_finish else None,
                "slip_days": slip_days,
                "is_critical": bool(c.get("is_critical")),
                "is_longest_path": bool(c.get("is_longest_path")),
                "total_float_hours": c.get("total_float_hours"),
                "status": c.get("status"),
                "percent_complete": int(c.get("percent_complete") or 0),
            }
        )

    removed = [
        {"external_id": p["external_id"], "name": p.get("name")}
        for p in prev
        if p["external_id"] not in curr_by_extid and p["external_id"] not in matched_prev_extids
    ]

    slipped.sort(key=lambda r: (not r["is_critical"], -r["slip_days"]))

    return {
        "slipped": slipped,
        "added": added,
        "removed": removed,
        "summary": {
            "slipped_count": len(slipped),
            "critical_slipped_count": sum(1 for r in slipped if r["is_critical"] or r["is_longest_path"]),
            "worst_slip_days": max((r["slip_days"] for r in slipped), default=0),
            "total_added": len(added),
            "total_removed": len(removed),
        },
    }
