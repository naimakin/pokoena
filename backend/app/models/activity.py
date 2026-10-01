import enum
import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.db.base import Base
from app.models.calendar import Calendar

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class ActivityStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    complete = "complete"


# P6's TASK.status_code for each of our statuses.
P6_STATUS_CODE = {
    ActivityStatus.not_started: "TK_NotStart",
    ActivityStatus.in_progress: "TK_Active",
    ActivityStatus.complete: "TK_Complete",
}

# P6 milestone task types: TT_Mile is a start milestone (one date, its Start),
# TT_FinMile a finish milestone (one date, its Finish). A milestone is never in
# progress — recording its one actual date completes it.
START_MILESTONE = "TT_Mile"
FINISH_MILESTONE = "TT_FinMile"
MILESTONE_TYPES = frozenset({START_MILESTONE, FINISH_MILESTONE})


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    project_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_scopes.id"), nullable=True, index=True
    )
    external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    discipline: Mapped[str] = mapped_column(String(120), nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    percent_complete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[ActivityStatus] = mapped_column(
        SAEnum(ActivityStatus, name="activity_status"),
        nullable=False,
        default=ActivityStatus.not_started,
    )

    # --- Team annotations, owned by Poko rather than P6 ---------------------
    # Set from the Activity modal and deliberately NOT touched by .xer import,
    # unlike everything in the P6 block below: an activity's dates come from the
    # programme, but "we flagged this one" is the team's own note on it and has
    # to survive every re-import.
    is_important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Site / supply risk ("high" | "standard" | "low"; None = not assessed, scored
    # as standard) — the Criticality Score input P6 doesn't carry
    # (services/criticality.py).
    site_risk: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- P6/CPM fields, populated by .xer import (backend/app/services/xer_import.py). ---
    # `remaining_duration_days` above stays the field the subcontractor scope page
    # reads/writes; these are read-only, CPM-derived, and overwritten wholesale on
    # every re-import (see xer_import.py for the exact create-vs-update field policy).
    clndr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calendars.id"), nullable=True, index=True)
    wbs_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # P6's TASK.phys_complete_pct. Not necessarily what Poko shows as % —
    # `percent_complete` is the displayed % (services/activity_progress.py::
    # display_percent); this is the physical % that round-trips to P6.
    phys_complete_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    remaining_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    early_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    early_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    late_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    late_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_float_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_float_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    constraint_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    constraint_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # P6's secondary constraint (cstr_type2/cstr_date2) — a task can carry two
    # simultaneous constraints (e.g. "Start On" + "Mandatory Finish"). Needed for
    # DCMA check #5 (hard constraints) to be fully faithful.
    constraint_type_2: Mapped[str | None] = mapped_column(String(30), nullable=True)
    constraint_date_2: Mapped[date | None] = mapped_column(Date, nullable=True)
    # True longest-path criticality (scheduler.py's BFS-backward `lp_critical`),
    # distinct from `is_critical` (TF<=0) — DCMA check #13 flags activities that
    # are TF=0 but NOT on the longest path ("artificial" criticality).
    is_longest_path: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_imports.id"), nullable=True, index=True
    )
    # P6's own internal task_id (distinct from `external_id`/task_code, the
    # human-readable activity ID). Used as-is on XER export
    # (engine/export/xer_writer.py) so re-importing into the SAME P6 project
    # updates these activities rather than creating duplicates. None for
    # activities that originated in Poko rather than an .xer import.
    p6_task_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # The activity's own calendar day length (Calendar.hours_per_day, i.e. P6's
    # CALENDAR.day_hr_cnt) — the divisor for showing any of the hour fields
    # above in days. Read-only, loaded with the row as a correlated subquery so
    # every consumer converts with the right calendar without a lookup of its
    # own; None when the activity has no calendar (see engine/durations.py for
    # the fallback).
    hours_per_day: Mapped[float | None] = column_property(
        select(Calendar.hours_per_day).where(Calendar.id == clndr_id).correlate_except(Calendar).scalar_subquery()
    )
