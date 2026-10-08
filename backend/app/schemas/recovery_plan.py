import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- slip report ------------------------------------------------------------


class SlipImportRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision_label: str | None
    data_date: datetime | None
    imported_at: datetime


class PlanLinkOut(BaseModel):
    id: uuid.UUID
    status: str
    revision_no: int
    item_count: int
    submitted_at: datetime | None = None


class SlipRowOut(BaseModel):
    external_id: str
    p6_task_id: str | None
    name: str | None
    wbs_path: str | None
    prev_finish: date | None
    curr_finish: date | None
    slip_days: int
    is_critical: bool
    is_longest_path: bool
    status: str | None
    percent_complete: int
    activity_id: uuid.UUID | None
    scope_id: uuid.UUID | None
    scope_name: str | None
    plan_required: bool
    needs_attention: bool
    plan: PlanLinkOut | None


class SlipCoverageOut(BaseModel):
    from_snapshot: bool
    to_snapshot: bool


class SlipSummaryOut(BaseModel):
    slipped_count: int
    critical_slipped_count: int
    worst_slip_days: int
    total_added: int
    total_removed: int
    plans_required: int
    plans_submitted: int
    plans_accepted: int


class SlipBaselineOut(BaseModel):
    """The project's active baseline — what From = "Baseline" compares against."""

    label: str
    import_id: uuid.UUID
    data_date: datetime | None


class SlipReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    # previous_upd / baseline_programme: the default pair; custom: a chosen
    # pair; baseline: From = the active baseline; none: nothing to compare.
    comparison_basis: Literal["previous_upd", "baseline_programme", "baseline", "custom", "none"]
    from_import: SlipImportRefOut | None
    to_import: SlipImportRefOut | None
    threshold_days: int
    coverage: SlipCoverageOut
    # True when nothing was chosen, or the choice equals the default pair.
    is_default: bool = True
    from_baseline: bool = False
    baseline: SlipBaselineOut | None = None
    summary: SlipSummaryOut
    slipped: list[SlipRowOut]


# --- recovery plan + items -------------------------------------------------


class RecoveryPlanCreate(BaseModel):
    activity_external_id: str = Field(min_length=1, max_length=50)
    summary: str | None = Field(default=None, max_length=4000)
    # The comparison the plan is raised against (the page's From / To); left
    # out = the default comparison. Recorded on the plan.
    from_import_id: uuid.UUID | None = None
    to_import_id: uuid.UUID | None = None
    from_baseline: bool = False


class RecoveryPlanHeaderUpdate(BaseModel):
    summary: str | None = Field(default=None, max_length=4000)


class RecoveryItemCreate(BaseModel):
    action: str = Field(min_length=1, max_length=2000)
    owner_name: str | None = Field(default=None, max_length=255)
    # A person who can see the activity; wins over owner_name.
    owner_user_id: uuid.UUID | None = None
    target_date: date | None = None


class RecoveryItemUpdate(BaseModel):
    action: str | None = Field(default=None, min_length=1, max_length=2000)
    # Sent alone, owner_name is a free-text owner and clears owner_user_id;
    # owner_user_id (null clears) picks a person and takes their name.
    owner_name: str | None = Field(default=None, max_length=255)
    owner_user_id: uuid.UUID | None = None
    target_date: date | None = None
    status: Literal["open", "in_progress", "done", "dropped"] | None = None
    completed_at: date | None = None


class RecoveryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recovery_plan_id: uuid.UUID
    order_index: int
    action: str
    owner_name: str | None
    owner_user_id: uuid.UUID | None = None
    target_date: date | None
    status: str
    completed_at: date | None


class RecoveryPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    activity_external_id: str
    activity_id: uuid.UUID | None
    activity_name: str
    wbs_path: str | None
    project_scope_id: uuid.UUID | None
    status: str
    revision_no: int
    summary: str | None
    created_by_user_id: uuid.UUID
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None
    review_note: str | None
    slip_days_at_creation: int | None
    from_import_id: uuid.UUID | None = None
    to_import_id: uuid.UUID | None = None
    submitted_by_user_id: uuid.UUID | None = None
    edited_at: datetime | None = None
    edited_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    # transient, filled by the route
    author_name: str | None = None
    scope_name: str | None = None
    submitted_by_name: str | None = None
    reviewed_by_name: str | None = None
    edited_by_name: str | None = None
    # "submission" / "acknowledgement" when the author changed the plan after
    # it was submitted / acknowledged (the status stays as it was).
    edited_after: Literal["submission", "acknowledgement"] | None = None
    # The comparison the plan was raised against, for display.
    from_label: str | None = None
    to_label: str | None = None
    # May the caller change the root cause and action items?
    can_edit: bool = False


class RecoveryPlanDetailOut(RecoveryPlanOut):
    items: list[RecoveryItemOut] = []


class ItemOrderIn(BaseModel):
    ordered_item_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class PlanReviewIn(BaseModel):
    decision: Literal["accept", "needs_revision"]
    note: str | None = Field(default=None, max_length=2000)


class BulkReviewIn(BaseModel):
    plan_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    decision: Literal["accept", "needs_revision"]
    note: str | None = Field(default=None, max_length=2000)
