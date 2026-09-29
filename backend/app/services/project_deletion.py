"""Permanently deletes a project and every row anywhere in the schema that
belongs to it — Portfolio > Projects' delete action. There is no soft-delete /
archive concept for a project; this is genuinely irreversible, which is why
the route this backs requires typing the project's code to confirm (see
api/routes/projects.py) and why this module exists as one auditable place
that enumerates every table a project's data can live in, rather than leaving
future features to remember to wire their own table into some generic
cascade.

None of the ~25 `project_id` foreign keys in this schema are
`ON DELETE CASCADE` (deliberately — see the two exceptions below), so this
walks the dependency graph bottom-up by hand: every DELETE here must run
before the row(s) it points at are deleted, or Postgres raises a
ForeignKeyViolation. The two child tables that DO cascade at the DB level —
recovery_plan_items (-> recovery_plans) and risk_action_items (-> risk_items)
— are deliberately not touched here; deleting their parent is enough.

Every query is additionally scoped by `tenant_id` (RLS already restricts the
session to one tenant for the whole request, but per CLAUDE.md's two-layer
rule this never relies on that alone).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.activity_event import ActivityEvent
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.activity_relationship import ActivityRelationship
from app.models.baseline import (
    Baseline,
    BaselineActivity,
    BaselinePvCurve,
    BaselineResource,
    BaselineResourceAssignment,
)
from app.models.calendar import Calendar
from app.models.change_request import ChangeRequest
from app.models.dashboard_layout import DashboardLayout
from app.models.evm_snapshot import EvmSnapshot
from app.models.progress_entry import ProgressEntry
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import RecoveryPlan
from app.models.report_format import ReportFormat
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.risk_item import RiskItem
from app.models.saved_activity_filter import SavedActivityFilter
from app.models.schedule_export import ScheduleExport
from app.models.schedule_import import ScheduleImport
from app.models.schedule_status_snapshot import ScheduleStatusSnapshot
from app.models.scope_submission import ScopeSubmission
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.update_period import UpdatePeriod
from app.models.wbs_node import WbsNode


def delete_project(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """Deletes every row belonging to `project_id`, then the project itself.
    Does not commit — the caller owns the transaction boundary (so a route can
    still roll back cleanly if something after this raises)."""

    def gone(model, **filters):
        # Query.filter() takes positional criteria, not kwargs — build them.
        criteria = [model.tenant_id == tenant_id] + [getattr(model, k) == v for k, v in filters.items()]
        db.query(model).filter(*criteria).delete(synchronize_session=False)

    update_period_ids = db.query(UpdatePeriod.id).filter(
        UpdatePeriod.tenant_id == tenant_id, UpdatePeriod.project_id == project_id
    )
    project_scope_ids = db.query(ProjectScope.id).filter(
        ProjectScope.tenant_id == tenant_id, ProjectScope.project_id == project_id
    )
    baseline_ids = db.query(Baseline.id).filter(Baseline.tenant_id == tenant_id, Baseline.project_id == project_id)

    # 1. Rows that reference an update period / project scope / activity
    # relationship, none of which cascade — must go before those tables.
    db.query(ChangeRequest).filter(
        ChangeRequest.tenant_id == tenant_id, ChangeRequest.update_period_id.in_(update_period_ids)
    ).delete(synchronize_session=False)
    db.query(ScopeSubmission).filter(
        ScopeSubmission.tenant_id == tenant_id, ScopeSubmission.update_period_id.in_(update_period_ids)
    ).delete(synchronize_session=False)
    db.query(SubcontractorScopeAssignment).filter(
        SubcontractorScopeAssignment.tenant_id == tenant_id,
        SubcontractorScopeAssignment.project_scope_id.in_(project_scope_ids),
    ).delete(synchronize_session=False)

    # 2. Rows keyed directly by project_id that other project-scoped tables
    # (activities, baselines, schedule_imports, activity_code_types) still
    # point at — must go before those.
    gone(EvmSnapshot, project_id=project_id)
    gone(TaskActivityCode, project_id=project_id)
    gone(ResourceAssignment, project_id=project_id)
    gone(ActivityRelationship, project_id=project_id)
    gone(ActivityEvent, project_id=project_id)
    gone(ProgressEntry, project_id=project_id)
    gone(RecoveryPlan, project_id=project_id)  # cascades to recovery_plan_items

    db.query(BaselineResourceAssignment).filter(
        BaselineResourceAssignment.tenant_id == tenant_id, BaselineResourceAssignment.baseline_id.in_(baseline_ids)
    ).delete(synchronize_session=False)
    db.query(BaselineResource).filter(
        BaselineResource.tenant_id == tenant_id, BaselineResource.baseline_id.in_(baseline_ids)
    ).delete(synchronize_session=False)
    db.query(BaselinePvCurve).filter(
        BaselinePvCurve.tenant_id == tenant_id, BaselinePvCurve.baseline_id.in_(baseline_ids)
    ).delete(synchronize_session=False)
    db.query(BaselineActivity).filter(
        BaselineActivity.tenant_id == tenant_id, BaselineActivity.baseline_id.in_(baseline_ids)
    ).delete(synchronize_session=False)

    gone(ScheduleStatusSnapshot, project_id=project_id)
    gone(ActivityCodeValue, project_id=project_id)

    # 3. Now safe: baselines (activities/schedule_imports still intact under
    # them), risk items (cascades to risk_action_items), then activities
    # itself (everything that pointed at an activity is gone above).
    gone(Baseline, project_id=project_id)
    gone(RiskItem, project_id=project_id)
    gone(Activity, project_id=project_id)

    # 4. Tables activities/baselines pointed at, now unreferenced.
    gone(ActivityCodeType, project_id=project_id)
    # schedule_exports and schedule_imports reference EACH OTHER (an import
    # names the export it came back from; an export names the programme it was
    # built from), so neither can simply go first. Cutting one direction here
    # leaves the other free to delete in order: exports keep their rows until
    # step 5, imports go now.
    db.query(ScheduleExport).filter(
        ScheduleExport.tenant_id == tenant_id, ScheduleExport.project_id == project_id
    ).update({ScheduleExport.source_import_id: None}, synchronize_session=False)
    gone(ScheduleImport, project_id=project_id)
    gone(Calendar, project_id=project_id)

    # 5. Tables update_periods/project_scopes pointed at are gone (step 1), so
    # they themselves are safe to drop now, along with everything else that's
    # keyed by project_id but nothing else depends on.
    gone(UpdatePeriod, project_id=project_id)
    gone(ProjectScope, project_id=project_id)
    gone(Resource, project_id=project_id)  # after resource_assignments, step 2
    gone(WbsNode, project_id=project_id)
    gone(DashboardLayout, project_id=project_id)
    gone(SavedActivityFilter, project_id=project_id)
    gone(ReportFormat, project_id=project_id)
    gone(ProjectMembership, project_id=project_id)
    gone(ScheduleExport, project_id=project_id)  # after schedule_imports, step 4

    db.query(Project).filter(Project.tenant_id == tenant_id, Project.id == project_id).delete(
        synchronize_session=False
    )
