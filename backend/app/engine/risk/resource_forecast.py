"""Resource-based finish forecast — "at the rate this job has actually been
earning its work, when does the remaining work run out?"

The logic-driven QSRA (qsra.py) answers "when, given the network and the
risks?". This answers the question a site manager asks first: there are W units
of work content left (manhours, m³, tonnes…), the job has demonstrated τ units
a week, so it needs about W / τ weeks — and since τ varies between updates, a
range rather than one number.

Everything is derived from what successive P6 updates already contain:
  - earned units at each update = Σ budget × physical % (per assignment), from
    the frozen activity snapshots — no timesheets needed;
  - actual units at each update from the assignment snapshots, where captured —
    giving the productivity factor PF = earned / actual;
  - the planned distribution from the baseline (or the target dates).

Method (after the research brief's section D):
  - per update period j: τ_j = ΔEU / Δweeks (earned units per week);
  - demonstrated rate = recency-weighted mean of the last four τ_j (1/2/3/4);
  - the forecast treats the rate as ONE sustained value for the whole remainder
    — productivity is autocorrelated, and independent weekly draws average out
    into a falsely narrow range. ln τ is taken as normal around the weighted
    mean of ln τ_j, σ = max(0.10, sd) × √(1 + 1/m), so the remaining time is
    lognormal and its P10/P50/P90 are closed-form:
        T_p = W · exp(−μ + z_p σ)   (weeks)
  - capacity cap: the P10 rate never exceeds 1.15 × the best of the
    demonstrated and planned peak weekly rates — the earliest credible finish
    never assumes productivity the job has never shown;
  - needs 3 update periods with progress; below that it says so instead of
    inventing a range.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional, Sequence

_Z10, _Z90 = -1.2815516, 1.2815516
_CAPACITY_HEADROOM = 1.15
_MIN_PERIODS = 3


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _working_days(start: date, end: date) -> list[date]:
    if end < start:
        start, end = end, start
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days or [start]


def spread_weekly(qty: float, start: Optional[date], end: Optional[date], into: dict[date, float]) -> None:
    """Spread `qty` evenly over the working days start..end into week buckets."""
    if not qty or start is None:
        return
    days = _working_days(start, end or start)
    per_day = qty / len(days)
    for d in days:
        wk = week_start(d)
        into[wk] = into.get(wk, 0.0) + per_day


@dataclass
class AssignmentInput:
    activity_key: str  # external_id
    budget: float
    actual: float
    remaining: float  # P6's remaining units
    percent_complete: float  # physical %, live
    planned_start: Optional[date]
    planned_finish: Optional[date]
    forecast_start: Optional[date]
    forecast_finish: Optional[date]


@dataclass
class UpdatePoint:
    label: str
    data_date: date
    earned: float  # Σ budget × % at that update
    actual: Optional[float]  # Σ actual units, when the assignment snapshot exists


@dataclass
class Period:
    label: str
    start: date
    end: date
    weeks: float
    earned: float
    actual: Optional[float]
    rate: float  # earned units / week
    productivity: Optional[float]  # earned / actual in the period


@dataclass
class WeekRow:
    week: date
    planned: float
    earned: float
    actual: float
    remaining: float


@dataclass
class Forecast:
    budget: float
    earned: float
    actual: float
    work_left: float  # W = budget − earned
    remaining_p6: float
    periods: list[Period]
    weeks: list[WeekRow]
    demonstrated_rate: Optional[float]
    best_rate: Optional[float]
    planned_peak_rate: Optional[float]
    required_rate: Optional[float]
    rate_ratio: Optional[float]  # required / demonstrated
    cumulative_productivity: Optional[float]  # earned / actual to date
    finish_p10: Optional[date]
    finish_p50: Optional[date]
    finish_p90: Optional[date]
    capped: bool
    method: str  # "demonstrated" | "insufficient" | "complete"
    notes: list[str] = field(default_factory=list)


def forecast(
    assignments: Sequence[AssignmentInput],
    history: Sequence[UpdatePoint],
    data_date: date,
    *,
    target_finish: Optional[date] = None,
) -> Forecast:
    notes: list[str] = []
    budget = sum(a.budget for a in assignments)
    earned = sum(a.budget * max(0.0, min(100.0, a.percent_complete)) / 100.0 for a in assignments)
    actual = sum(a.actual for a in assignments)
    work_left = max(0.0, budget - earned)
    remaining_p6 = sum(max(0.0, a.remaining) for a in assignments)

    planned: dict[date, float] = {}
    remaining_w: dict[date, float] = {}
    for a in assignments:
        spread_weekly(a.budget, a.planned_start, a.planned_finish, planned)
        if a.remaining > 0:
            start = a.forecast_start if a.forecast_start and a.forecast_start > data_date else data_date
            finish = a.forecast_finish if a.forecast_finish and a.forecast_finish >= start else start
            spread_weekly(a.remaining, start, finish, remaining_w)

    points = sorted((h for h in history if h.data_date <= data_date), key=lambda h: h.data_date)
    periods: list[Period] = []
    earned_w: dict[date, float] = {}
    actual_w: dict[date, float] = {}
    for p0, p1 in zip(points, points[1:]):
        if p1.data_date <= p0.data_date:
            continue
        weeks = (p1.data_date - p0.data_date).days / 7.0
        d_earned = p1.earned - p0.earned
        d_actual = (p1.actual - p0.actual) if (p1.actual is not None and p0.actual is not None) else None
        pf = d_earned / d_actual if d_actual and d_actual >= 0.02 * max(budget, 1e-9) else None
        periods.append(Period(p1.label, p0.data_date, p1.data_date, round(weeks, 2), round(d_earned, 2),
                              round(d_actual, 2) if d_actual is not None else None,
                              round(d_earned / weeks, 2) if weeks > 0 else 0.0,
                              round(pf, 3) if pf is not None else None))
        if d_earned > 0:
            spread_weekly(d_earned, p0.data_date + timedelta(days=1), p1.data_date, earned_w)
        if d_actual and d_actual > 0:
            spread_weekly(d_actual, p0.data_date + timedelta(days=1), p1.data_date, actual_w)

    weeks_all = sorted(set(planned) | set(earned_w) | set(actual_w) | set(remaining_w))
    rows = [
        WeekRow(w, round(planned.get(w, 0.0), 2), round(earned_w.get(w, 0.0), 2),
                round(actual_w.get(w, 0.0), 2), round(remaining_w.get(w, 0.0), 2))
        for w in weeks_all
    ]

    progressing = [p for p in periods if p.rate > 0 and p.weeks > 0]
    recent = progressing[-4:]
    weights = list(range(1, len(recent) + 1))
    demonstrated = (
        sum(p.rate * w for p, w in zip(recent, weights)) / sum(weights) if recent else None
    )
    best = max((p.rate for p in progressing), default=None)
    planned_peak = max(planned.values(), default=None) if planned else None

    required = None
    if target_finish and work_left > 0:
        weeks_left = (target_finish - data_date).days / 7.0
        if weeks_left > 0:
            required = work_left / weeks_left
        else:
            notes.append("The target finish is already behind the data date.")
    ratio = required / demonstrated if required and demonstrated else None
    cpf = earned / actual if actual > 0 else None

    p10 = p50 = p90 = None
    capped = False
    if work_left <= 0:
        method = "complete"
        p10 = p50 = p90 = data_date
    elif len(progressing) < _MIN_PERIODS:
        method = "insufficient"
        notes.append(
            f"Needs {_MIN_PERIODS} update periods with progress to forecast from demonstrated productivity "
            f"(has {len(progressing)}). Each schedule update adds one."
        )
    else:
        method = "demonstrated"
        logs = [math.log(p.rate) for p in recent]
        mu = sum(l * w for l, w in zip(logs, weights)) / sum(weights)
        m = len(logs)
        mean_l = sum(logs) / m
        sd = math.sqrt(sum((l - mean_l) ** 2 for l in logs) / (m - 1)) if m > 1 else 0.0
        sigma = max(0.10, sd) * math.sqrt(1 + 1 / m)

        def weeks_at(z: float) -> float:
            return work_left * math.exp(-mu + z * sigma)

        w10, w50, w90 = weeks_at(_Z10), weeks_at(0.0), weeks_at(_Z90)
        cap_rate = _CAPACITY_HEADROOM * max(best or 0.0, planned_peak or 0.0)
        if cap_rate > 0 and work_left / w10 > cap_rate:
            w10 = work_left / cap_rate
            capped = True
        p10 = data_date + timedelta(days=round(w10 * 7))
        p50 = data_date + timedelta(days=round(w50 * 7))
        p90 = data_date + timedelta(days=round(w90 * 7))
        if m < 4:
            notes.append(f"Based on {m} update periods — the range narrows as more updates come in.")

    return Forecast(
        budget=round(budget, 2), earned=round(earned, 2), actual=round(actual, 2), work_left=round(work_left, 2),
        remaining_p6=round(remaining_p6, 2), periods=periods, weeks=rows,
        demonstrated_rate=round(demonstrated, 2) if demonstrated else None,
        best_rate=round(best, 2) if best else None,
        planned_peak_rate=round(planned_peak, 2) if planned_peak else None,
        required_rate=round(required, 2) if required else None,
        rate_ratio=round(ratio, 2) if ratio else None,
        cumulative_productivity=round(cpf, 3) if cpf else None,
        finish_p10=p10, finish_p50=p50, finish_p90=p90, capped=capped, method=method, notes=notes,
    )
