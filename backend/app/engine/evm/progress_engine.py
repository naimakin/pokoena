"""Planned vs actual progress — the pair every schedule-analytics tool leads
with (Nodes & Links' Progress Summary, P6's Schedule % vs Activity %).

Both sides are duration-weighted percentages over the same activity set:

  planned % = share of the BASELINE's duration that the baseline itself had
              finished by the data date (each activity's baseline hours spread
              evenly across its baseline start..finish, calendar days inclusive
              — the same distribution `scurve_engine.generate_pv_curve` stores);
  actual %  = share of the CURRENT schedule's duration earned so far
              (sum of target hours x percent complete / sum of target hours —
              the same figure the status pages show as "% complete");
  SPI       = actual % / planned %.

Level of Effort and WBS Summary rows are left out of both: neither is work in
its own right, and an LOE spanning the whole project would otherwise outweigh
dozens of real activities. Milestones carry no duration so they weigh nothing.

The data date is the first day not yet statused (P6 convention), so work
planned ON the data date doesn't count as due yet.

Pure functions over plain values — the caller loads the rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

NON_PROGRESS_TASK_TYPES = {"TT_WBS", "TT_LOE"}
MILESTONE_TASK_TYPES = {"TT_Mile", "TT_FinMile"}


def counts_toward_progress(task_type: Optional[str]) -> bool:
    return (task_type or "") not in NON_PROGRESS_TASK_TYPES


def planned_fraction(start: Optional[date], finish: Optional[date], data_date: date) -> float:
    """Share of [start, finish] (calendar days, inclusive) that lies before
    `data_date`. Matches the per-day spread of `generate_pv_curve`."""
    if start is None or finish is None:
        return 0.0
    if finish < start:
        start, finish = finish, start
    span = (finish - start).days + 1
    elapsed = (data_date - start).days
    return min(max(elapsed / span, 0.0), 1.0)


def planned_percent(rows: Iterable[tuple[float, Optional[date], Optional[date]]], data_date: date) -> Optional[float]:
    """`rows` — (baseline hours, baseline start, baseline finish) per activity.
    None when nothing in the baseline carries any duration."""
    total = done = 0.0
    for hours, start, finish in rows:
        if not hours or hours <= 0:
            continue
        total += hours
        done += hours * planned_fraction(start, finish, data_date)
    if total <= 0:
        return None
    return round(done / total * 100.0, 2)


def actual_percent(rows: Iterable[tuple[float, float]]) -> Optional[float]:
    """`rows` — (target hours, percent complete 0-100) per activity."""
    total = earned = 0.0
    for hours, pct in rows:
        if not hours or hours <= 0:
            continue
        total += hours
        earned += hours * min(max(pct or 0.0, 0.0), 100.0) / 100.0
    if total <= 0:
        return None
    return round(earned / total * 100.0, 2)


def schedule_performance(planned_pct: Optional[float], actual_pct: Optional[float]) -> Optional[float]:
    """Actual over planned. Before the baseline plans any work there is nothing
    to fall behind on — PMI's zero state is 1.0, not "cannot compute"."""
    if planned_pct is None or actual_pct is None:
        return None
    if planned_pct <= 0:
        return 1.0 if actual_pct <= 0 else None
    return round(actual_pct / planned_pct, 4)


@dataclass(frozen=True)
class VersionFacts:
    """One programme version's headline numbers — a row of the baseline vs
    latest table."""

    start: Optional[date]
    finish: Optional[date]
    milestones_total: int
    milestones_remaining: int
    tasks_total: int
    tasks_remaining: int
    max_wbs_level: int


@dataclass(frozen=True)
class VersionRow:
    task_type: Optional[str]
    start: Optional[date]
    finish: Optional[date]
    wbs_path: Optional[str]
    is_remaining: bool


def version_facts(rows: Iterable[VersionRow]) -> VersionFacts:
    """Milestones are TT_Mile/TT_FinMile; tasks are every other activity that
    counts toward progress (so not WBS Summary or LOE)."""
    starts: list[date] = []
    finishes: list[date] = []
    milestones = milestones_open = tasks = tasks_open = 0
    max_level = 0
    for r in rows:
        if not counts_toward_progress(r.task_type):
            continue
        if r.start:
            starts.append(r.start)
        if r.finish:
            finishes.append(r.finish)
        if (r.task_type or "") in MILESTONE_TASK_TYPES:
            milestones += 1
            milestones_open += r.is_remaining
        else:
            tasks += 1
            tasks_open += r.is_remaining
        if r.wbs_path:
            max_level = max(max_level, len([p for p in r.wbs_path.split(" > ") if p]))
    return VersionFacts(
        start=min(starts) if starts else None,
        finish=max(finishes) if finishes else None,
        milestones_total=milestones,
        milestones_remaining=milestones_open,
        tasks_total=tasks,
        tasks_remaining=tasks_open,
        max_wbs_level=max_level,
    )
