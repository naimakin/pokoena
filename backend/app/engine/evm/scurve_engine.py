"""S-Curve & EVM time-series engine — ported from the reference project's
`backend/app/engine/evm/scurve_engine.py` (263 lines) plus the query logic
from `evm_database.py`, adapted to take plain Python data pre-loaded from our
Postgres tables by the caller (`app/api/routes/evm.py`) instead of owning a
raw SQLite connection — matching every other engine module in this codebase
(engine/quality/dcma.py, engine/risk/monte_carlo.py, etc. are all pure
functions over lists, not DB-connection-owning modules).

Two academic building blocks, unchanged from the reference:
  - PMI Practice Standard for EVM: before any work is performed (EV=0, AC=0),
    SPI/CPI are 1.0 by definition — no deviation exists yet to measure.
  - Christensen (1998): EV = sum(percent_complete/100 * target_duration_hours)
    across activities — a duration-weighted "earned effort" measure. This is
    the reference's `compute_current_ev`, renamed field-for-field to our
    `Activity.percent_complete`/`target_duration_hours`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import groupby
from typing import Optional

from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship

TCPI_CRITICAL_THRESHOLD = 1.10  # Anbari (2003)


@dataclass(frozen=True)
class EvmPoint:
    snapshot_date: date
    pv_cumulative: float
    ev_cumulative: float
    ac_cumulative: float
    bac: float
    spi: Optional[float]
    cpi: Optional[float]
    sv: float
    cv: float
    eac: Optional[float]
    etc: Optional[float]
    tcpi: Optional[float]
    percent_complete_planned: float
    percent_complete_earned: float
    tcpi_critical: bool

    @classmethod
    def compute(cls, snapshot_date: date, pv_cum: float, ev_cum: float, ac_cum: float, bac: float) -> "EvmPoint":
        # PMI Practice Standard for EVM: before any work is performed
        # (EV=0, AC=0), indices are 1.0 by definition — nothing to measure yet.
        if ev_cum == 0 and ac_cum == 0:
            spi = 1.0
            cpi = 1.0
        else:
            spi = round(ev_cum / pv_cum, 4) if pv_cum > 0 else None
            cpi = round(ev_cum / ac_cum, 4) if ac_cum > 0 else None
        sv = round(ev_cum - pv_cum, 4)
        cv = round(ev_cum - ac_cum, 4)
        eac = round(bac / cpi, 4) if cpi and cpi > 0 else None
        etc = round(eac - ac_cum, 4) if eac is not None else None
        denom = bac - ac_cum
        tcpi = round((bac - ev_cum) / denom, 4) if denom > 0 else None
        return cls(
            snapshot_date=snapshot_date,
            pv_cumulative=round(pv_cum, 4),
            ev_cumulative=round(ev_cum, 4),
            ac_cumulative=round(ac_cum, 4),
            bac=round(bac, 4),
            spi=spi, cpi=cpi, sv=sv, cv=cv, eac=eac, etc=etc, tcpi=tcpi,
            percent_complete_planned=round(pv_cum / bac * 100, 2) if bac > 0 else 0.0,
            percent_complete_earned=round(ev_cum / bac * 100, 2) if bac > 0 else 0.0,
            tcpi_critical=(tcpi is not None and tcpi > TCPI_CRITICAL_THRESHOLD),
        )


def generate_pv_curve(activities: list[dict], bac: float) -> list[tuple[date, float, float]]:
    """Linear distribution: each activity's planned_manhours spread uniformly
    across its baseline_start..baseline_end span. `activities` is a list of
    dicts with `planned_manhours`/`baseline_start`/`baseline_end` keys (the
    shape `api/routes/evm.py` builds from `BaselineActivity` rows). Returns
    `[(curve_date, pv_daily, pv_cumulative), ...]`, stored once at baseline
    lock time in `baseline_pv_curve`."""
    if not activities or bac <= 0:
        return []

    valid = [
        a for a in activities
        if a.get("planned_manhours", 0) > 0 and a.get("baseline_start") and a.get("baseline_end")
    ]
    if not valid:
        return []

    project_start = min(a["baseline_start"] for a in valid)
    project_end = max(a["baseline_end"] for a in valid)

    daily_pv: dict[date, float] = {}
    for act in valid:
        mh = float(act["planned_manhours"])
        s = act["baseline_start"]
        e = act["baseline_end"]
        dur = max((e - s).days + 1, 1)
        per_day = mh / dur
        cur = s
        while cur <= e:
            daily_pv[cur] = daily_pv.get(cur, 0.0) + per_day
            cur += timedelta(days=1)

    result: list[tuple[date, float, float]] = []
    running = 0.0
    cur = project_start
    while cur <= project_end:
        d = round(daily_pv.get(cur, 0.0), 4)
        running = round(running + d, 4)
        result.append((cur, d, running))
        cur += timedelta(days=1)

    return result


def compute_current_ev(activities: list[Activity]) -> float:
    """EV = sum(percent_complete/100 x target_duration_hours) — Christensen
    (1998) weighted method."""
    return round(
        sum(
            (a.percent_complete or 0) / 100.0 * (a.target_duration_hours or 0)
            for a in (activities or [])
        ),
        4,
    )


def compute_evm_series(
    pv_series: dict[date, float],
    ac_series: dict[date, float],
    bac: float,
    current_ev: float,
) -> list[EvmPoint]:
    """Build the full EVM point series across the union of PV/AC dates. EV is
    projected as a step function: 0 until the first date with a reported
    actual, then `current_ev` from then on — same "current EV applies
    retroactively once work starts" behavior as the reference."""
    all_dates = sorted(set(pv_series) | set(ac_series))
    if not all_dates:
        return []

    first_ac_date = min(ac_series) if ac_series else None

    points: list[EvmPoint] = []
    for d in all_dates:
        pv_cum = pv_series.get(d, 0.0)
        ac_cum = ac_series.get(d, 0.0)
        ev_cum = current_ev if (first_ac_date and d >= first_ac_date) else 0.0
        points.append(EvmPoint.compute(d, pv_cum, ev_cum, ac_cum, bac))
    return points


def aggregate_granularity(points: list[EvmPoint], granularity: str) -> list[EvmPoint]:
    """Downsample daily EVM points to weekly or monthly — takes the last point
    of each period, since this is a cumulative series (the last value in a
    period is already correct)."""
    if granularity == "daily" or not points:
        return points

    def period_key(pt: EvmPoint) -> str:
        d = pt.snapshot_date
        if granularity == "weekly":
            iso = d.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        return d.strftime("%Y-%m")

    return [list(group)[-1] for _key, group in groupby(points, key=period_key)]


def find_out_of_sequence_activities(
    activities: list[Activity], relationships: list[ActivityRelationship], reported_activity_ids: set[uuid.UUID]
) -> set[uuid.UUID]:
    """Activities with reported progress (>0% complete) where at least one
    predecessor is still at 0% — a sign progress was logged out of the
    planned sequence. Only considers activities that actually have a
    progress_entries row (`reported_activity_ids`)."""
    pct_map = {a.id: (a.percent_complete or 0) for a in activities}
    pred_map: dict[uuid.UUID, set[uuid.UUID]] = {}
    for rel in relationships:
        pred_map.setdefault(rel.successor_id, set()).add(rel.predecessor_id)

    out_of_sequence: set[uuid.UUID] = set()
    for activity_id in reported_activity_ids:
        predecessors = pred_map.get(activity_id)
        if not predecessors:
            continue
        if pct_map.get(activity_id, 0) <= 0:
            continue
        if any(pct_map.get(pred_id, 0) <= 0 for pred_id in predecessors):
            out_of_sequence.add(activity_id)
    return out_of_sequence
