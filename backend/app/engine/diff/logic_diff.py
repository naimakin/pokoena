"""Logic Diff — compares the relationship snapshots captured at two different
.xer imports of the same project and reports ADDED/REMOVED/MODIFIED
relationships. Ported from the reference project's
`backend/app/engine/diff/logic_change_detector.py`, adapted to operate on the
lightweight JSON relationship snapshot captured on each `ScheduleImport` row
(see `services/xer_import.py`) instead of two full parsed-schedule snapshots —
we don't keep full versioned snapshots (`ScheduleImport` is audit/history, not
a versioned schedule graph — see its docstring), only enough per-import data
to diff relationships specifically.

Key: (pred_external_id, succ_external_id) — lag is NOT part of the key, so a
relationship that only changed its lag is reported as MODIFIED rather than
REMOVED+ADDED. Lag changes smaller than `lag_threshold_hours` (default 8h /
1 work day) are treated as noise and ignored, same as the reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

DEFAULT_LAG_THRESHOLD_HOURS = 8.0


@dataclass
class RelationshipChange:
    pred_external_id: str
    pred_name: str
    succ_external_id: str
    succ_name: str
    change_type: str  # ADDED | REMOVED | MODIFIED
    changes: list[str] = field(default_factory=list)  # TYPE_CHANGED, LAG_CHANGED
    old_link_type: Optional[str] = None
    new_link_type: Optional[str] = None
    old_lag_hours: Optional[float] = None
    new_lag_hours: Optional[float] = None
    pred_was_critical: bool = False
    succ_was_critical: bool = False


def _rel_map(snapshot: list[dict]) -> dict[tuple[str, str], dict]:
    m: dict[tuple[str, str], dict] = {}
    for r in snapshot:
        key = (r["pred_external_id"], r["succ_external_id"])
        if key not in m:  # keep first occurrence (edge case: duplicate pairs)
            m[key] = r
    return m


def compare_relationship_snapshots(
    snapshot_a: list[dict],
    snapshot_b: list[dict],
    lag_threshold_hours: float = DEFAULT_LAG_THRESHOLD_HOURS,
) -> tuple[dict, list[RelationshipChange]]:
    """snapshot_a = older/"from", snapshot_b = newer/"to". Returns
    (summary_dict, changes) where summary_dict has added/removed/modified/total counts."""
    rels_a = _rel_map(snapshot_a)
    rels_b = _rel_map(snapshot_b)
    keys_a, keys_b = set(rels_a), set(rels_b)

    results: list[RelationshipChange] = []

    for key in sorted(keys_b - keys_a):
        r = rels_b[key]
        results.append(
            RelationshipChange(
                pred_external_id=r["pred_external_id"],
                pred_name=r["pred_name"],
                succ_external_id=r["succ_external_id"],
                succ_name=r["succ_name"],
                change_type="ADDED",
                new_link_type=r["link_type"],
                new_lag_hours=r["lag_hours"],
            )
        )

    for key in sorted(keys_a - keys_b):
        r = rels_a[key]
        results.append(
            RelationshipChange(
                pred_external_id=r["pred_external_id"],
                pred_name=r["pred_name"],
                succ_external_id=r["succ_external_id"],
                succ_name=r["succ_name"],
                change_type="REMOVED",
                old_link_type=r["link_type"],
                old_lag_hours=r["lag_hours"],
                pred_was_critical=r.get("pred_critical", False),
                succ_was_critical=r.get("succ_critical", False),
            )
        )

    for key in sorted(keys_a & keys_b):
        ra, rb = rels_a[key], rels_b[key]
        type_changed = ra["link_type"] != rb["link_type"]
        lag_changed = abs(rb["lag_hours"] - ra["lag_hours"]) >= lag_threshold_hours
        if not type_changed and not lag_changed:
            continue

        sub: list[str] = []
        if type_changed:
            sub.append("TYPE_CHANGED")
        if lag_changed:
            sub.append("LAG_CHANGED")

        results.append(
            RelationshipChange(
                pred_external_id=ra["pred_external_id"],
                pred_name=ra["pred_name"],
                succ_external_id=ra["succ_external_id"],
                succ_name=ra["succ_name"],
                change_type="MODIFIED",
                changes=sub,
                old_link_type=ra["link_type"],
                new_link_type=rb["link_type"] if type_changed else None,
                old_lag_hours=ra["lag_hours"] if lag_changed else None,
                new_lag_hours=rb["lag_hours"] if lag_changed else None,
                pred_was_critical=ra.get("pred_critical", False),
                succ_was_critical=ra.get("succ_critical", False),
            )
        )

    added = sum(1 for c in results if c.change_type == "ADDED")
    removed = sum(1 for c in results if c.change_type == "REMOVED")
    modified = sum(1 for c in results if c.change_type == "MODIFIED")
    summary = {"added": added, "removed": removed, "modified": modified, "total": len(results)}

    return summary, results
