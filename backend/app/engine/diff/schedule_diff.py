"""Schedule diff between two .xer import snapshots — the full "what changed
between UPD-n-1 and UPD-n" comparison behind Execution → Changes.

Activities: added / removed / renamed / modified (per-field). Relationships:
delegated to engine/diff/logic_diff.compare_relationship_snapshots. Pure
functions over the JSON blobs frozen on ScheduleImport by
services/xer_import.py. New per-activity keys (start dates, durations,
constraints) only appear on imports created after they were added — every
field check below is skipped unless BOTH snapshots carry the key, so a
comparison that spans the change degrades gracefully.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from app.engine.diff.logic_diff import RelationshipChange, compare_relationship_snapshots

_START_KEYS = ("actual_start", "planned_start", "early_start")
_FINISH_KEYS = ("actual_finish", "planned_finish", "early_finish")

_LOGIC_SIGN = {"ADDED": "+", "REMOVED": "−", "MODIFIED": "~"}
_LOGIC_DETAIL_LIMIT = 6


def _parse(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _pick(snap: dict, keys: tuple[str, ...]) -> date | None:
    for k in keys:
        d = _parse(snap.get(k))
        if d is not None:
            return d
    return None


def _has_any(snap: dict, keys: tuple[str, ...]) -> bool:
    return any(k in snap for k in keys)


def _field(field: str, label: str, old, new, **extra) -> dict:
    return {
        "field": field, "label": label, "old": old, "new": new,
        "delta_days": None, "delta_hours": None, "detail": None, **extra,
    }


def _diff_activity(
    prev: dict, curr: dict, *, date_threshold_days: int, duration_threshold_hours: float
) -> list[dict]:
    fields: list[dict] = []

    if prev.get("name") != curr.get("name"):
        fields.append(_field("name", "Name", prev.get("name"), curr.get("name")))

    pf, cf = _pick(prev, _FINISH_KEYS), _pick(curr, _FINISH_KEYS)
    if pf and cf and abs((cf - pf).days) >= date_threshold_days:
        fields.append(
            {"field": "finish", "label": "Finish", "old": pf.isoformat(), "new": cf.isoformat(),
             "delta_days": (cf - pf).days, "delta_hours": None}
        )

    if _has_any(prev, _START_KEYS) and _has_any(curr, _START_KEYS):
        ps, cs = _pick(prev, _START_KEYS), _pick(curr, _START_KEYS)
        if ps and cs and abs((cs - ps).days) >= date_threshold_days:
            fields.append(
                {"field": "start", "label": "Start", "old": ps.isoformat(), "new": cs.isoformat(),
                 "delta_days": (cs - ps).days, "delta_hours": None}
            )

    # Original vs remaining duration are different questions: the first says the
    # plan was re-scoped, the second says work is being burned down (or isn't).
    # P6 keeps both, so report both rather than one "Duration".
    for key, field_name, label in (
        ("target_duration_hours", "duration", "Original duration (d)"),
        ("remaining_duration_hours", "remaining_duration", "Remaining duration (d)"),
    ):
        po, cu = prev.get(key), curr.get(key)
        if po is None or cu is None or abs(cu - po) < duration_threshold_hours:
            continue
        # Stored in hours, read in days — P6's own unit for a duration column.
        fields.append(
            _field(
                field_name, label, round(po / 8.0, 1), round(cu / 8.0, 1),
                delta_days=round((cu - po) / 8.0, 1),
            )
        )

    if prev.get("status") and curr.get("status") and prev["status"] != curr["status"]:
        fields.append(
            {"field": "status", "label": "Status", "old": prev["status"], "new": curr["status"],
             "delta_days": None, "delta_hours": None}
        )

    pp, cp = prev.get("percent_complete"), curr.get("percent_complete")
    if pp is not None and cp is not None and pp != cp:
        fields.append(
            {"field": "percent_complete", "label": "% Complete", "old": pp, "new": cp,
             "delta_days": None, "delta_hours": None}
        )

    was_crit, is_crit = bool(prev.get("is_critical")), bool(curr.get("is_critical"))
    if was_crit != is_crit:
        fields.append(
            {"field": "criticality", "label": "Critical path",
             "old": "critical" if was_crit else "not critical",
             "new": "critical" if is_crit else "not critical",
             "delta_days": None, "delta_hours": None}
        )

    if "constraint_type" in prev and "constraint_type" in curr:
        p_key = (prev.get("constraint_type") or None, prev.get("constraint_date") or None)
        c_key = (curr.get("constraint_type") or None, curr.get("constraint_date") or None)
        if p_key != c_key:
            fields.append(
                {"field": "constraint", "label": "Constraint",
                 "old": f"{p_key[0] or '—'} {p_key[1] or ''}".strip(),
                 "new": f"{c_key[0] or '—'} {c_key[1] or ''}".strip(),
                 "delta_days": None, "delta_hours": None}
            )

    if prev.get("wbs_path") != curr.get("wbs_path"):
        fields.append(
            {"field": "wbs", "label": "WBS", "old": prev.get("wbs_path"), "new": curr.get("wbs_path"),
             "delta_days": None, "delta_hours": None}
        )

    ptf, ctf = prev.get("total_float_hours"), curr.get("total_float_hours")
    if ptf is not None and ctf is not None:
        delta_days = round((ctf - ptf) / 8.0, 1)
        if abs(delta_days) >= date_threshold_days:
            fields.append(
                {"field": "total_float", "label": "Total float (d)",
                 "old": round(ptf / 8.0, 1), "new": round(ctf / 8.0, 1),
                 "delta_days": delta_days, "delta_hours": None}
            )

    return fields


def _link_counts(rels: list[dict]) -> Counter:
    """How many relationships each activity sits on, either end."""
    counts: Counter = Counter()
    for r in rels or []:
        counts[r["pred_external_id"]] += 1
        counts[r["succ_external_id"]] += 1
    return counts


def _describe_link(c: RelationshipChange, ext_id: str) -> str:
    """One line of a logic change, written from `ext_id`'s point of view: an
    arrow into it for a predecessor, out of it for a successor."""
    other, arrow = (
        (c.pred_external_id, "←") if c.succ_external_id == ext_id else (c.succ_external_id, "→")
    )
    link = c.new_link_type or c.old_link_type or ""
    if c.change_type == "MODIFIED":
        bits = []
        if c.old_link_type != c.new_link_type:
            bits.append(f"{c.old_link_type} → {c.new_link_type}")
        if c.old_lag_hours != c.new_lag_hours:
            bits.append(f"lag {c.old_lag_hours}h → {c.new_lag_hours}h")
        link = ", ".join(bits) or link
    elif c.new_lag_hours or c.old_lag_hours:
        link = f"{link} lag {c.new_lag_hours if c.change_type == 'ADDED' else c.old_lag_hours}h"
    return f"{_LOGIC_SIGN[c.change_type]} {arrow} {other} {link}".rstrip()


def _logic_by_activity(
    rel_changes: list[RelationshipChange], prev_rels: list[dict], curr_rels: list[dict]
) -> dict[str, dict]:
    """Per-activity view of the relationship diff, so "did this activity's logic
    change?" is answerable on the activity row rather than only in the separate
    Logic changes table."""
    touched: dict[str, list[RelationshipChange]] = {}
    for c in rel_changes:
        for ext_id in (c.pred_external_id, c.succ_external_id):
            touched.setdefault(ext_id, []).append(c)

    before, after = _link_counts(prev_rels), _link_counts(curr_rels)
    out: dict[str, dict] = {}
    for ext_id, changes in touched.items():
        detail = [_describe_link(c, ext_id) for c in changes[:_LOGIC_DETAIL_LIMIT]]
        if len(changes) > _LOGIC_DETAIL_LIMIT:
            detail.append(f"+{len(changes) - _LOGIC_DETAIL_LIMIT} more")
        out[ext_id] = {
            "old": f"{before.get(ext_id, 0)} links",
            "new": f"{after.get(ext_id, 0)} links",
            "detail": detail,
        }
    return out


def compute_schedule_diff(
    prev_acts: list[dict],
    curr_acts: list[dict],
    prev_rels: list[dict],
    curr_rels: list[dict],
    *,
    date_threshold_days: int = 1,
    duration_threshold_hours: float = 8.0,
    lag_threshold_hours: float = 8.0,
) -> dict:
    prev_by_ext = {a["external_id"]: a for a in prev_acts}
    curr_by_ext = {a["external_id"]: a for a in curr_acts}
    prev_by_p6 = {a["p6_task_id"]: a for a in prev_acts if a.get("p6_task_id")}

    # Logic first: each surviving activity gets its own relationship changes
    # folded in as a field, so an activity that was only re-linked still shows
    # up under Modified instead of only in the Logic changes table.
    rel_summary, rel_changes = compare_relationship_snapshots(prev_rels, curr_rels, lag_threshold_hours)
    logic_by_ext = _logic_by_activity(rel_changes, prev_rels, curr_rels)

    added: list[dict] = []
    removed: list[dict] = []
    renamed: list[dict] = []
    modified: list[dict] = []
    matched_prev: set[str] = set()

    for c in curr_acts:
        p = prev_by_ext.get(c["external_id"])
        is_rename = False
        if p is None and c.get("p6_task_id"):
            cand = prev_by_p6.get(c["p6_task_id"])
            if cand is not None and cand["external_id"] not in curr_by_ext:
                p = cand
                is_rename = True

        if p is None:
            added.append(
                {
                    "external_id": c["external_id"],
                    "name": c.get("name"),
                    "wbs_path": c.get("wbs_path"),
                    "planned_finish": c.get("planned_finish"),
                    "is_critical": bool(c.get("is_critical")),
                }
            )
            continue

        matched_prev.add(p["external_id"])
        if is_rename:
            renamed.append(
                {"old_external_id": p["external_id"], "new_external_id": c["external_id"], "name": c.get("name")}
            )

        fields = _diff_activity(
            p, c, date_threshold_days=date_threshold_days, duration_threshold_hours=duration_threshold_hours
        )
        # A rename is also an Activity ID change — it has its own section, but
        # repeat it here so a row read on its own is complete.
        if is_rename:
            fields.insert(0, _field("external_id", "Activity ID", p["external_id"], c["external_id"]))
        logic = logic_by_ext.get(c["external_id"]) or (
            logic_by_ext.get(p["external_id"]) if is_rename else None
        )
        if logic:
            fields.append(
                _field(
                    "logic", "Logic", logic["old"], logic["new"],
                    detail=logic["detail"],
                )
            )
        if fields:
            modified.append(
                {
                    "external_id": c["external_id"],
                    "name": c.get("name"),
                    "wbs_path": c.get("wbs_path"),
                    "is_critical": bool(c.get("is_critical")),
                    "fields": fields,
                }
            )

    for p in prev_acts:
        if p["external_id"] not in curr_by_ext and p["external_id"] not in matched_prev:
            removed.append(
                {"external_id": p["external_id"], "name": p.get("name"), "was_critical": bool(p.get("is_critical"))}
            )

    modified.sort(key=lambda m: (not m["is_critical"], -len(m["fields"])))

    date_changes = sum(
        1 for m in modified if any(f["field"] in ("start", "finish") for f in m["fields"])
    )
    crit_changes = sum(
        1 for m in modified if any(f["field"] == "criticality" for f in m["fields"])
    )

    return {
        "activities": {"added": added, "removed": removed, "renamed": renamed, "modified": modified},
        "relationships": {
            "summary": rel_summary,
            "changes": [c.__dict__ for c in rel_changes],
        },
        "summary": {
            "activities_added": len(added),
            "activities_removed": len(removed),
            "activities_renamed": len(renamed),
            "activities_modified": len(modified),
            "date_changes": date_changes,
            "criticality_changes": crit_changes,
            "relationships_added": rel_summary["added"],
            "relationships_removed": rel_summary["removed"],
            "relationships_modified": rel_summary["modified"],
        },
    }
