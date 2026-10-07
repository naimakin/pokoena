"""Which activities belong to a subcontractor scope, by rule.

A ProjectScope names its activities by P6 WBS (`wbs_ids`, each node with its
whole subtree) and/or P6 activity code values (`code_value_ids`, each value
with its child values). Both are stored as P6's own ids (PROJWBS.wbs_id,
ACTVCODE.actv_code_id), never Poko row ids, so a rule survives every re-import
of the programme. Matching works like a P6 filter:

- an activity is in a selected WBS subtree, if any WBS is selected; AND
- for every code type with a selected value, the activity carries one of the
  selected values of that type (OR within a type, AND across types).

The result is materialised on `Activity.project_scope_id` — what every scope
guard (deps.require_scope_access) and list filter already reads — after each
rule change and each import. An activity matching several scopes goes to the
oldest one. Activities sitting in a scope that has no rules (assigned some
other way) are left alone.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.project_scope import ProjectScope
from app.models.wbs_node import WbsNode


@dataclass(frozen=True)
class ScopeRules:
    wbs_ids: frozenset[str]
    code_value_ids: frozenset[str]

    @property
    def is_empty(self) -> bool:
        return not self.wbs_ids and not self.code_value_ids

    @classmethod
    def of(cls, scope: ProjectScope) -> "ScopeRules":
        return cls(frozenset(scope.wbs_ids or []), frozenset(scope.code_value_ids or []))


def _descendants(roots: frozenset[str], children: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node in out:
            continue
        out.add(node)
        stack.extend(children.get(node, []))
    return out


class _ProjectIndex:
    """The project's WBS tree, code values and per-activity code assignments,
    loaded once so any number of rule sets can be matched against them."""

    def __init__(self, db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID):
        self.wbs_children: dict[str, list[str]] = {}
        for wbs_id, parent in (
            db.query(WbsNode.wbs_id, WbsNode.parent_wbs_id)
            .filter(WbsNode.tenant_id == tenant_id, WbsNode.project_id == project_id)
            .all()
        ):
            if parent:
                self.wbs_children.setdefault(parent, []).append(wbs_id)

        type_key = {
            row_id: p6_id
            for row_id, p6_id in db.query(ActivityCodeType.id, ActivityCodeType.actv_code_type_id)
            .filter(ActivityCodeType.tenant_id == tenant_id, ActivityCodeType.project_id == project_id)
            .all()
        }
        self.code_type_of: dict[str, str] = {}
        self.code_children: dict[str, list[str]] = {}
        value_key: dict[uuid.UUID, str] = {}
        for row_id, code_id, type_row_id, parent in (
            db.query(
                ActivityCodeValue.id,
                ActivityCodeValue.actv_code_id,
                ActivityCodeValue.code_type_id,
                ActivityCodeValue.parent_actv_code_id,
            )
            .filter(ActivityCodeValue.tenant_id == tenant_id, ActivityCodeValue.project_id == project_id)
            .all()
        ):
            value_key[row_id] = code_id
            self.code_type_of[code_id] = type_key.get(type_row_id, "")
            if parent:
                self.code_children.setdefault(parent, []).append(code_id)

        self.codes_by_activity: dict[uuid.UUID, set[str]] = {}
        for activity_id, value_row_id in (
            db.query(TaskActivityCode.activity_id, TaskActivityCode.code_value_id)
            .filter(TaskActivityCode.tenant_id == tenant_id, TaskActivityCode.project_id == project_id)
            .all()
        ):
            code_id = value_key.get(value_row_id)
            if code_id:
                self.codes_by_activity.setdefault(activity_id, set()).add(code_id)

    def matcher(self, rules: ScopeRules):
        wbs = _descendants(rules.wbs_ids, self.wbs_children) if rules.wbs_ids else None
        by_type: dict[str, set[str]] = {}
        for code_id in rules.code_value_ids:
            by_type.setdefault(self.code_type_of.get(code_id, ""), set()).update(
                _descendants(frozenset({code_id}), self.code_children)
            )

        def matches(activity: Activity) -> bool:
            if rules.is_empty:
                return False
            if wbs is not None and activity.wbs_path not in wbs:
                return False
            codes = self.codes_by_activity.get(activity.id, set())
            return all(codes & wanted for wanted in by_type.values())

        return matches


def _scopes(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> list[ProjectScope]:
    return (
        db.query(ProjectScope)
        .filter(ProjectScope.tenant_id == tenant_id, ProjectScope.project_id == project_id)
        .order_by(ProjectScope.created_at, ProjectScope.id)
        .all()
    )


def _activities(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> list[Activity]:
    return (
        db.query(Activity)
        .filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id,
                or_(Activity.task_type.is_(None), Activity.task_type != "TT_WBS"))
        .all()
    )


def preview(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, rules: ScopeRules) -> list[Activity]:
    """The activities these rules would select (before any overlap with other scopes)."""
    if rules.is_empty:
        return []
    matches = _ProjectIndex(db, tenant_id, project_id).matcher(rules)
    return [a for a in _activities(db, tenant_id, project_id) if matches(a)]


def apply_scope_rules(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Re-assign the project's activities to its rule-based scopes. Returns the
    number of activities now in each scope. Flushes, never commits."""
    scopes = _scopes(db, tenant_id, project_id)
    ruled = [(s, ScopeRules.of(s)) for s in scopes]
    ruled = [(s, r) for s, r in ruled if not r.is_empty]
    ruled_ids = {s.id for s, _ in ruled}
    manual_ids = {s.id for s in scopes} - ruled_ids

    index = _ProjectIndex(db, tenant_id, project_id)
    matchers = [(s.id, index.matcher(r)) for s, r in ruled]

    counts: dict[uuid.UUID, int] = {s.id: 0 for s in scopes}
    for activity in _activities(db, tenant_id, project_id):
        if activity.project_scope_id in manual_ids:
            counts[activity.project_scope_id] += 1
            continue
        target = next((scope_id for scope_id, matches in matchers if matches(activity)), None)
        if activity.project_scope_id != target:
            activity.project_scope_id = target
        if target is not None:
            counts[target] += 1
    db.flush()
    return counts


def scope_activity_counts(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
    return dict(
        db.query(Activity.project_scope_id, func.count(Activity.id))
        .filter(
            Activity.tenant_id == tenant_id,
            Activity.project_id == project_id,
            Activity.project_scope_id.isnot(None),
        )
        .group_by(Activity.project_scope_id)
        .all()
    )
