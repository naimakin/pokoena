"""Monte Carlo schedule risk simulation — ported from the reference project's
`backend/app/engine/risk/monte_carlo.py` (359 lines), with `numpy` swapped for
the standard library. This project doesn't add new pip dependencies without
confirming with the user first, and numpy there is only used for three things:
vectorized triangular sampling, percentile, and histogram binning — none of
which the per-iteration simplified CPM forward pass (`_run_iteration`) needed
in the first place; that was already a plain Python loop. `random.triangular`
plus a small linear-interpolation percentile function and manual histogram
binning cover the same ground. The trade-off: without vectorized sampling,
very high iteration counts get slower on large projects, so our max is capped
at 5,000 rather than the reference's 110,000.

Also ported faithfully: the reference's own "simplified calendar" choice for
this engine specifically — `duration_days = sampled_hours / hours_per_day`,
weekend-unaware `timedelta` arithmetic. That's a deliberate speed/accuracy
trade-off for a routine that runs the forward pass hundreds-to-thousands of
times per request; it does NOT affect the real, calendar-aware CPM used by
the XER import path (`engine/cpm/scheduler.py` + `CalendarEngine`).
"""

from __future__ import annotations

import logging
import random
import statistics
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship, LinkType

logger = logging.getLogger(__name__)

DEFAULT_ITERATIONS = 1_000
MAX_ITERATIONS = 5_000  # capped well below the reference's 110k — no vectorized sampling here
DEFAULT_SPREAD = 0.20

_MILESTONE_TYPES = {"TT_Mile", "TT_FinMile", "TT_StartMile"}
_CRITICAL_TOLERANCE_SECONDS = 3600  # within 1 hour of project finish = "on the critical path"


@dataclass
class ActivityRiskOverride:
    activity_id: uuid.UUID
    optimistic: float
    most_likely: float
    pessimistic: float


@dataclass
class MonteCarloResult:
    iterations: int
    project_finish_p10: datetime
    project_finish_p50: datetime
    project_finish_p80: datetime
    project_finish_p90: datetime
    mean_finish: datetime
    histogram: list[dict]
    critical_activities: list[str]  # external_ids on the critical path in >50% of runs


def _topo_sort(ids: list[uuid.UUID], rels: list[ActivityRelationship]) -> list[uuid.UUID]:
    in_deg: dict[uuid.UUID, int] = {i: 0 for i in ids}
    adj: dict[uuid.UUID, list[uuid.UUID]] = {i: [] for i in ids}
    for r in rels:
        if r.predecessor_id in in_deg and r.successor_id in in_deg:
            adj[r.predecessor_id].append(r.successor_id)
            in_deg[r.successor_id] += 1

    queue = deque(sorted((i for i, d in in_deg.items() if d == 0), key=str))
    order: list[uuid.UUID] = []
    while queue:
        t = queue.popleft()
        order.append(t)
        for s in sorted(adj[t], key=str):
            in_deg[s] -= 1
            if in_deg[s] == 0:
                queue.append(s)
    return order  # cycle members are silently dropped — surfaced by the real scheduler on import


def _build_risk_map(
    activities: list[Activity], overrides: list[ActivityRiskOverride], spread: float
) -> dict[uuid.UUID, tuple[float, float, float]]:
    override_map = {o.activity_id: o for o in overrides}
    risk_map: dict[uuid.UUID, tuple[float, float, float]] = {}

    for act in activities:
        if act.id in override_map:
            o = override_map[act.id]
            risk_map[act.id] = (o.optimistic, o.most_likely, o.pessimistic)
            continue

        if act.status_code == "TK_Complete" or act.task_type in _MILESTONE_TYPES:
            risk_map[act.id] = (0.0, 0.0, 0.0)
            continue

        ml = act.remaining_duration_hours or act.target_duration_hours or 0.0
        if ml <= 0:
            risk_map[act.id] = (0.0, 0.0, 0.0)
            continue
        risk_map[act.id] = (ml * (1 - spread), ml, ml * (1 + spread))

    return risk_map


def _sample(low: float, mode: float, high: float) -> float:
    if low >= high:
        return mode
    return random.triangular(low, high, mode)


def _as_dt(d: Optional[date]) -> Optional[datetime]:
    if d is None:
        return None
    return datetime(d.year, d.month, d.day)


def _run_iteration(
    order: list[uuid.UUID],
    acts: dict[uuid.UUID, Activity],
    pred_adj: dict[uuid.UUID, list[tuple[uuid.UUID, LinkType, float]]],
    durations: dict[uuid.UUID, float],
    hpd_map: dict[Optional[uuid.UUID], float],
    default_hpd: float,
    data_date: datetime,
) -> dict[uuid.UUID, datetime]:
    """Returns {activity_id: early_finish} for all activities, using the
    simplified (weekend-unaware) calendar described in the module docstring."""
    es: dict[uuid.UUID, datetime] = {}
    ef: dict[uuid.UUID, datetime] = {}

    for tid in order:
        act = acts[tid]
        hpd = hpd_map.get(act.clndr_id, default_hpd) or default_hpd
        dur_hr = durations[tid]

        if act.status_code == "TK_Complete":
            es[tid] = _as_dt(act.actual_start) or data_date
            ef[tid] = _as_dt(act.actual_finish) or data_date
            continue

        t_es = (_as_dt(act.actual_start) if act.status_code == "TK_Active" else None) or data_date

        for pred_id, link_type, lag_hours in pred_adj.get(tid, []):
            p_es = es.get(pred_id, data_date)
            p_ef = ef.get(pred_id, data_date)
            lag_days = lag_hours / hpd if hpd > 0 else 0.0

            if link_type == LinkType.FS:
                candidate = p_ef + timedelta(days=lag_days)
            elif link_type == LinkType.SS:
                candidate = p_es + timedelta(days=lag_days)
            else:
                dur_days = dur_hr / hpd if hpd > 0 else 0.0
                base = p_ef if link_type == LinkType.FF else p_es
                candidate = base + timedelta(days=lag_days) - timedelta(days=dur_days)

            if candidate > t_es:
                t_es = candidate

        if act.status_code == "TK_Active":
            actual_start = _as_dt(act.actual_start)
            if actual_start and t_es < actual_start:
                t_es = actual_start

        es[tid] = t_es
        dur_days = dur_hr / hpd if hpd > 0 else 0.0
        ef[tid] = t_es + timedelta(days=dur_days)

    return ef


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _build_histogram(sorted_offsets: list[float], iterations: int, base: datetime, bins: int = 30) -> list[dict]:
    """`sorted_offsets` are seconds-from-`base` (not epoch timestamps — see
    the module-level note on why: naive datetime<->timestamp round-trips are
    silently local-timezone-dependent, which would make results differ
    between a dev machine and the UTC production container)."""
    if not sorted_offsets:
        return []
    lo, hi = sorted_offsets[0], sorted_offsets[-1]
    if lo == hi:
        return [
            {"date": (base + timedelta(seconds=lo)).strftime("%Y-%m-%d"), "count": iterations, "cumulative_pct": 100.0}
        ]

    width = (hi - lo) / bins
    counts = [0] * bins
    for off in sorted_offsets:
        idx = min(int((off - lo) / width), bins - 1)
        counts[idx] += 1

    histogram = []
    cumulative = 0
    for i, cnt in enumerate(counts):
        cumulative += cnt
        bin_offset = lo + i * width
        histogram.append(
            {
                "date": (base + timedelta(seconds=bin_offset)).strftime("%Y-%m-%d"),
                "count": cnt,
                "cumulative_pct": round(cumulative / iterations * 100, 2),
            }
        )
    return histogram


def _deterministic_result(proj_end: datetime, iterations: int) -> MonteCarloResult:
    return MonteCarloResult(
        iterations=iterations,
        project_finish_p10=proj_end,
        project_finish_p50=proj_end,
        project_finish_p80=proj_end,
        project_finish_p90=proj_end,
        mean_finish=proj_end,
        histogram=[{"date": proj_end.strftime("%Y-%m-%d"), "count": iterations, "cumulative_pct": 100.0}],
        critical_activities=[],
    )


def run_monte_carlo(
    activities: list[Activity],
    relationships: list[ActivityRelationship],
    calendars_by_id: dict[uuid.UUID, float],
    default_hpd: float,
    data_date: Optional[datetime],
    iterations: int = DEFAULT_ITERATIONS,
    spread: float = DEFAULT_SPREAD,
    overrides: Optional[list[ActivityRiskOverride]] = None,
) -> MonteCarloResult:
    """Run Monte Carlo simulation on a project's current (already CPM-scheduled)
    activities. Raises ValueError on invalid input (no activities, spread < 0,
    or an override with optimistic > pessimistic)."""
    overrides = overrides or []
    iterations = max(1, min(iterations, MAX_ITERATIONS))
    if spread < 0:
        raise ValueError("spread must be >= 0")
    if not activities:
        raise ValueError("Project has no activities — cannot run simulation.")

    dd = data_date or datetime.utcnow()

    if all(a.status_code == "TK_Complete" for a in activities):
        proj_end = max((_as_dt(a.actual_finish) for a in activities if a.actual_finish), default=dd)
        return _deterministic_result(proj_end, iterations)

    acts_by_id = {a.id: a for a in activities}
    pred_adj: dict[uuid.UUID, list[tuple[uuid.UUID, LinkType, float]]] = {a.id: [] for a in activities}
    for r in relationships:
        if r.predecessor_id in acts_by_id and r.successor_id in acts_by_id:
            pred_adj[r.successor_id].append((r.predecessor_id, r.link_type, r.lag_hours or 0))

    order = _topo_sort(list(acts_by_id.keys()), relationships)
    risk_map = _build_risk_map(activities, overrides, spread)

    for tid in order:
        low, _mode, high = risk_map.get(tid, (0.0, 0.0, 0.0))
        if low > high:
            raise ValueError("One or more activities have optimistic > pessimistic duration — check overrides.")

    finish_dates: list[datetime] = []
    critical_counts: dict[uuid.UUID, int] = {tid: 0 for tid in order}

    for _ in range(iterations):
        durations = {tid: _sample(*risk_map.get(tid, (0.0, 0.0, 0.0))) for tid in order}
        ef_map = _run_iteration(order, acts_by_id, pred_adj, durations, calendars_by_id, default_hpd, dd)
        proj_finish = max(ef_map.values(), default=dd)
        finish_dates.append(proj_finish)
        for tid, ef_dt in ef_map.items():
            if abs((proj_finish - ef_dt).total_seconds()) < _CRITICAL_TOLERANCE_SECONDS:
                critical_counts[tid] += 1

    # Percentiles/mean/histogram are computed as second-offsets from a fixed
    # base datetime rather than via `.timestamp()`/`utcfromtimestamp()` — for
    # a naive datetime, that round-trip is silently local-timezone-dependent,
    # which would make results differ between a dev machine and the (UTC)
    # production container for the exact same inputs.
    base = min(finish_dates)
    offsets = sorted((d - base).total_seconds() for d in finish_dates)
    p10 = base + timedelta(seconds=_percentile(offsets, 10))
    p50 = base + timedelta(seconds=_percentile(offsets, 50))
    p80 = base + timedelta(seconds=_percentile(offsets, 80))
    p90 = base + timedelta(seconds=_percentile(offsets, 90))
    mean_dt = base + timedelta(seconds=statistics.mean(offsets))

    histogram = _build_histogram(offsets, iterations, base)

    threshold = iterations * 0.5
    critical_ids = {tid for tid, cnt in critical_counts.items() if cnt > threshold}
    critical_activities = [acts_by_id[tid].external_id for tid in order if tid in critical_ids]

    logger.info(
        "[MonteCarlo] %d iterations | P50=%s P80=%s P90=%s | %d critical activities",
        iterations,
        p50.strftime("%d-%b-%Y"),
        p80.strftime("%d-%b-%Y"),
        p90.strftime("%d-%b-%Y"),
        len(critical_activities),
    )

    return MonteCarloResult(
        iterations=iterations,
        project_finish_p10=p10,
        project_finish_p50=p50,
        project_finish_p80=p80,
        project_finish_p90=p90,
        mean_finish=mean_dt,
        histogram=histogram,
        critical_activities=critical_activities,
    )
