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

from datetime import date

from app.engine.diff.logic_diff import compare_relationship_snapshots

_START_KEYS = ("actual_start", "planned_start", "early_start")
_FINISH_KEYS = ("actual_finish", "planned_finish", "early_finish")


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


def _diff_activity(
    prev: dict, curr: dict, *, date_threshold_days: int, duration_threshold_hours: float
) -> list[dict]:
    fields: list[dict] = []

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

    pd, cd = prev.get("target_duration_hours"), curr.get("target_duration_hours")
    if pd is not None and cd is not None and abs(cd - pd) >= duration_threshold_hours:
        fields.append(
            {"field": "duration", "label": "Duration", "old": pd, "new": cd,
             "delta_days": None, "delta_hours": round(cd - pd, 1)}
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

    rel_summary, rel_changes = compare_relationship_snapshots(prev_rels, curr_rels, lag_threshold_hours)

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
