"""Quantitative schedule risk analysis (QSRA) — risk-driver Monte Carlo.

The older `monte_carlo.py` stretches every activity by the same ±X% and knows
nothing about the risk register. This engine is the method AACE RP 57R-09 and
Hulett's "risk driver" approach describe:

  - Background (inherent) uncertainty on every remaining activity: a 3-point
    range of factors on its remaining duration. It covers estimating error only
    — discrete events (weather, late delivery, a refused permit) belong in the
    register, never in both places. Factors are drawn through a Gaussian copula
    with a project-wide factor and a per-group (WBS) factor, so activities move
    together to a degree. Independent draws across hundreds of activities cancel
    out and give a falsely narrow, over-confident finish distribution.
  - Risk events from the register. Each occurs in an iteration with its
    probability; when it does, ONE sampled impact applies to every activity it
    is linked to — as a % stretch of their durations (Hulett's multiplicative
    driver, the default) or as working days added. A risk is one event, which
    is also what correlates the activities it touches.
  - A forward pass over the real logic network (FS/SS/FF/SF + lags), in working
    HOURS on the project calendar — plain float arithmetic, no datetimes in the
    loop. P-dates are converted to calendar dates once, afterwards, through the
    same CalendarEngine the CPM uses.

Common random numbers: every iteration seeds its own generator and draws in a
fixed order — project factor, group factors, one draw per uncertain activity,
then (occurrence, impact) per risk — whether or not a risk is switched on. Two
runs that differ only in one risk's probability or impact therefore differ only
by that change, which is what makes pre/post-mitigation and risk-ranking
comparisons clean.

Scope choices, each deliberate:
  - In-progress activities resume at the data date (progress override) — the
    rule the import-time CPM (engine/cpm/scheduler.py) uses, so the calibration
    run lands on the finish the rest of Poko shows.
  - "Start (on / on or after)" and mandatory-start constraints are floors on the
    early start, "finish (on / on or after)" and mandatory-finish floors on the
    early finish. "On or before" constraints and ALAP only move late dates and
    float, so they're ignored; hard dates would otherwise pin an activity
    against the very uncertainty being measured.

Pure standard library (no numpy — see monte_carlo.py for why).
"""

from __future__ import annotations

import bisect
import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

FS, SS, FF, SF = 0, 1, 2, 3

DEFAULT_ITERATIONS = 1_000
MAX_ITERATIONS = 5_000
_TIE_HOURS = 0.5
_MIN_COMBINED_FACTOR = 0.2
_SQRT2 = math.sqrt(2.0)


@dataclass
class SimActivity:
    """One activity, already reduced to project-calendar working hours."""

    key: object
    external_id: str
    name: str
    status: str  # "complete" | "active" | "not_started"
    remaining_hours: float
    is_milestone: bool = False
    fixed_finish_offset: float = 0.0  # completed: actual finish vs data date
    fixed_start_offset: float = 0.0  # completed / active: actual start vs data date
    start_floor_offset: Optional[float] = None
    finish_floor_offset: Optional[float] = None
    background: tuple[float, float, float] = (1.0, 1.0, 1.0)
    group: int = -1  # correlation group (WBS), -1 = none


@dataclass
class SimLink:
    pred: int
    succ: int
    kind: int
    lag_hours: float


@dataclass
class RiskDriver:
    """One register risk as the engine sees it. `impact` magnitudes are always
    positive: percent for duration_pct, working days for delay_days. An
    opportunity applies them with the opposite sign."""

    key: str
    title: str
    probability: float  # 0..1
    impact: tuple[float, float, float]
    distribution: str = "triangular"  # triangular | pert | uniform
    mode: str = "duration_pct"  # duration_pct | delay_days
    activity_indices: list[int] = field(default_factory=list)
    is_opportunity: bool = False
    _pert_table: Optional[tuple[list[float], list[float]]] = None


@dataclass
class DriverStat:
    key: str
    title: str
    probability: float
    occurred_pct: float
    delay_when_occurs_days: float  # mean T | occurred − mean T | not, working days
    expected_delay_days: float  # probability × the above
    critical_hit_pct: float  # occurred AND one of its activities drove the finish


@dataclass
class ActivityStat:
    index: int
    criticality_pct: float
    ssi: float  # criticality × σ(duration) / σ(finish)
    cruciality: float  # Pearson correlation of duration with the finish
    duration_sd_hours: float
    mean_duration_hours: float


@dataclass
class SimulationResult:
    iterations: int
    calibration_offset: float  # hours — every factor 1, no risks
    offsets_sorted: list[float]
    mean_offset: float
    sd_offset: float
    drivers: list[DriverStat]
    activities: list[ActivityStat] = field(default_factory=list)


# --- distributions --------------------------------------------------------------


def tri_inv(u: float, low: float, mode: float, high: float) -> float:
    """Inverse CDF of the triangular distribution."""
    if high <= low:
        return mode
    c = (mode - low) / (high - low)
    if u < c:
        return low + math.sqrt(u * (high - low) * (mode - low))
    return high - math.sqrt((1 - u) * (high - low) * (high - mode))


def _pert_table(low: float, mode: float, high: float, steps: int = 2000, points: int = 201):
    """CDF of Beta-PERT (lambda 4) tabulated by midpoint integration, so it can
    be inverted from a uniform draw — deterministic in u, hence CRN-safe."""
    a = 1 + 4 * (mode - low) / (high - low)
    b = 1 + 4 * (high - mode) / (high - low)
    dens = []
    for k in range(steps):
        x = (k + 0.5) / steps
        dens.append(x ** (a - 1) * (1 - x) ** (b - 1))
    total = sum(dens)
    cum = [0.0]
    running = 0.0
    for d in dens:
        running += d / total
        cum.append(running)
    xs = [k / steps for k in range(steps + 1)]
    # Thin to `points` evenly spaced probabilities.
    probs = [i / (points - 1) for i in range(points)]
    values = []
    for p in probs:
        j = bisect.bisect_left(cum, p)
        j = min(max(j, 1), len(cum) - 1)
        c0, c1 = cum[j - 1], cum[j]
        t = 0.0 if c1 == c0 else (p - c0) / (c1 - c0)
        values.append(low + (high - low) * (xs[j - 1] + t * (xs[j] - xs[j - 1])))
    return probs, values


def inv_impact(driver: RiskDriver, u: float) -> float:
    low, mode, high = driver.impact
    if high <= low:
        return mode
    if driver.distribution == "uniform":
        return low + (high - low) * u
    if driver.distribution == "pert":
        if driver._pert_table is None:
            driver._pert_table = _pert_table(low, mode, high)
        probs, values = driver._pert_table
        j = min(max(bisect.bisect_left(probs, u), 1), len(probs) - 1)
        p0, p1 = probs[j - 1], probs[j]
        t = 0.0 if p1 == p0 else (u - p0) / (p1 - p0)
        return values[j - 1] + t * (values[j] - values[j - 1])
    return tri_inv(u, low, mode, high)


def triangular_sd(low: float, mode: float, high: float) -> float:
    var = (low * low + mode * mode + high * high - low * mode - low * high - mode * high) / 18.0
    return math.sqrt(max(var, 0.0))


def percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


# --- network ----------------------------------------------------------------------


def topo_order(n: int, links: Iterable[SimLink]) -> list[int]:
    """Kahn's algorithm; members of a cycle are dropped (the import-time CPM
    already refuses cyclic schedules, so this only guards hand-built input)."""
    indeg = [0] * n
    adj: list[list[int]] = [[] for _ in range(n)]
    for link in links:
        adj[link.pred].append(link.succ)
        indeg[link.succ] += 1
    queue = deque(i for i in range(n) if indeg[i] == 0)
    order: list[int] = []
    while queue:
        i = queue.popleft()
        order.append(i)
        for s in adj[i]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    return order


class Network:
    """The activity network, pre-flattened for the hot loop."""

    def __init__(self, activities: Sequence[SimActivity], links: Sequence[SimLink], n_groups: int = 0):
        self.activities = list(activities)
        self.n = len(self.activities)
        self.order = topo_order(self.n, links)
        grouped: list[list[tuple[int, int, float]]] = [[] for _ in range(self.n)]
        for link in links:
            grouped[link.succ].append((link.pred, link.kind, link.lag_hours))
        self.preds = [tuple(g) for g in grouped]
        self.n_groups = n_groups
        self.uncertain = [
            i for i, a in enumerate(self.activities)
            if a.status != "complete" and not a.is_milestone and a.remaining_hours > 0
            and a.background[2] > a.background[0]
        ]
        self.base = [
            0.0 if (a.status == "complete" or a.is_milestone) else max(0.0, a.remaining_hours)
            for a in self.activities
        ]

    def forward_pass(self, durations: Sequence[float]) -> tuple[list[float], list[float]]:
        """(early start, early finish) offsets from the data date, in hours."""
        n = self.n
        es = [0.0] * n
        ef = [0.0] * n
        acts = self.activities
        preds = self.preds
        for i in self.order:
            a = acts[i]
            if a.status == "complete":
                es[i] = a.fixed_start_offset
                ef[i] = a.fixed_finish_offset
                continue
            d = durations[i]
            if a.status == "active":
                es[i] = min(a.fixed_start_offset, 0.0)
                finish = d
            else:
                start = 0.0
                for p, kind, lag in preds[i]:
                    if kind == FS:
                        c = ef[p] + lag
                    elif kind == SS:
                        c = es[p] + lag
                    elif kind == FF:
                        c = ef[p] + lag - d
                    else:
                        c = es[p] + lag - d
                    if c > start:
                        start = c
                floor = a.start_floor_offset
                if floor is not None and floor > start:
                    start = floor
                es[i] = start
                finish = start + d
            ffloor = a.finish_floor_offset
            ef[i] = ffloor if ffloor is not None and ffloor > finish else finish
        return es, ef

    def driving_path(self, es: list[float], ef: list[float], durations: Sequence[float], target: int) -> set[int]:
        """Activities on the driving path back from `target`."""
        on_path = {target}
        stack = [target]
        acts = self.activities
        while stack:
            i = stack.pop()
            a = acts[i]
            if a.status != "not_started":
                continue
            d = durations[i]
            # Finish held by its own floor: nothing upstream drove it.
            if a.finish_floor_offset is not None and ef[i] > es[i] + d + _TIE_HOURS:
                continue
            for p, kind, lag in self.preds[i]:
                if kind == FS:
                    c = ef[p] + lag
                elif kind == SS:
                    c = es[p] + lag
                elif kind == FF:
                    c = ef[p] + lag - d
                else:
                    c = es[p] + lag - d
                if c > -_TIE_HOURS and abs(c - es[i]) <= _TIE_HOURS and p not in on_path:
                    on_path.add(p)
                    stack.append(p)
        return on_path


# --- simulation --------------------------------------------------------------------


@dataclass
class CorrelationWeights:
    """Shares of variance (a² + b² + c² = 1) for the project factor, the group
    factor and the activity's own draw. Brief defaults: 0.10 / 0.20 / 0.70 —
    about 0.3 correlation inside a WBS group and 0.1 across groups."""

    project: float = 0.10
    group: float = 0.20

    def coefficients(self, has_groups: bool) -> tuple[float, float, float]:
        a2 = max(0.0, self.project)
        b2 = max(0.0, self.group) if has_groups else 0.0
        if not has_groups:
            a2 = min(1.0, a2 + max(0.0, self.group))
        c2 = max(0.0, 1.0 - a2 - b2)
        return math.sqrt(a2), math.sqrt(b2), math.sqrt(c2)


def simulate(
    network: Network,
    drivers: Sequence[RiskDriver],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    hours_per_day: float = 8.0,
    seed: int = 1,
    weights: CorrelationWeights | None = None,
    target_index: Optional[int] = None,
    track_activities: bool = True,
) -> SimulationResult:
    iterations = max(1, min(int(iterations), MAX_ITERATIONS))
    weights = weights or CorrelationWeights()
    acts = network.activities
    n = network.n
    base = network.base
    uncertain = network.uncertain
    uncertain_set = set(uncertain)
    ca, cb, cc = weights.coefficients(network.n_groups > 0)
    n_groups = network.n_groups
    groups = [a.group for a in acts]
    backgrounds = [a.background for a in acts]
    erf = math.erf

    def pick_target(ef: list[float]) -> int:
        if target_index is not None:
            return target_index
        return max(range(n), key=ef.__getitem__)

    # Calibration: every factor 1, no risk events — should reproduce the CPM.
    _es, cal_ef = network.forward_pass(base)
    calibration = cal_ef[pick_target(cal_ef)] if n else 0.0

    # Risks touching completed activities have no effect there.
    driver_targets = [[i for i in d.activity_indices if acts[i].status != "complete"] for d in drivers]

    finishes: list[float] = []
    occ_count = [0] * len(drivers)
    occ_sum = [0.0] * len(drivers)
    driver_critical = [0] * len(drivers)
    crit = [0] * n
    tracked = sorted(uncertain_set | {i for t in driver_targets for i in t}) if track_activities else []
    s_d = {i: 0.0 for i in tracked}
    s_dd = {i: 0.0 for i in tracked}
    s_dt = {i: 0.0 for i in tracked}

    for k in range(iterations):
        rng = random.Random(seed * 100003 + k)
        gauss = rng.gauss
        rand = rng.random

        z_project = gauss(0.0, 1.0)
        z_groups = [gauss(0.0, 1.0) for _ in range(n_groups)]
        durations = list(base)
        for i in uncertain:
            g = groups[i]
            z = ca * z_project + (cb * z_groups[g] if g >= 0 and n_groups else 0.0) + cc * gauss(0.0, 1.0)
            u = 0.5 * (1.0 + erf(z / _SQRT2))
            low, ml, high = backgrounds[i]
            durations[i] = base[i] * tri_inv(u, low, ml, high)

        factors: dict[int, float] = {}
        adds: dict[int, float] = {}
        hits = []
        for d_idx, drv in enumerate(drivers):
            u_occ = rand()
            u_imp = rand()
            hit = u_occ < drv.probability and bool(driver_targets[d_idx])
            hits.append(hit)
            if not hit:
                continue
            magnitude = inv_impact(drv, u_imp)
            sign = -1.0 if drv.is_opportunity else 1.0
            if drv.mode == "delay_days":
                delta = sign * magnitude * hours_per_day
                for i in driver_targets[d_idx]:
                    adds[i] = adds.get(i, 0.0) + delta
            else:
                f = 1.0 + sign * magnitude / 100.0
                for i in driver_targets[d_idx]:
                    factors[i] = factors.get(i, 1.0) * f

        for i, f in factors.items():
            durations[i] *= max(_MIN_COMBINED_FACTOR, f)
        for i, delta in adds.items():
            durations[i] = max(0.0, durations[i] + delta)

        es, ef = network.forward_pass(durations)
        t_idx = pick_target(ef) if n else 0
        finish = ef[t_idx] if n else 0.0
        finishes.append(finish)

        for d_idx, hit in enumerate(hits):
            if hit:
                occ_count[d_idx] += 1
                occ_sum[d_idx] += finish

        if track_activities and n:
            path = network.driving_path(es, ef, durations, t_idx)
            for i in path:
                crit[i] += 1
            for d_idx, hit in enumerate(hits):
                if hit and any(i in path for i in driver_targets[d_idx]):
                    driver_critical[d_idx] += 1
            for i in tracked:
                d = durations[i]
                s_d[i] += d
                s_dd[i] += d * d
                s_dt[i] += d * finish

    N = float(iterations)
    mean_t = sum(finishes) / N
    var_t = max(0.0, sum(f * f for f in finishes) / N - mean_t * mean_t)
    sd_t = math.sqrt(var_t)

    driver_stats: list[DriverStat] = []
    total_sum = sum(finishes)
    for d_idx, drv in enumerate(drivers):
        cnt = occ_count[d_idx]
        if 0 < cnt < iterations:
            with_mean = occ_sum[d_idx] / cnt
            without_mean = (total_sum - occ_sum[d_idx]) / (iterations - cnt)
            delta_h = with_mean - without_mean
        else:
            delta_h = 0.0
        delay_days = delta_h / hours_per_day if hours_per_day else 0.0
        driver_stats.append(
            DriverStat(
                key=drv.key,
                title=drv.title,
                probability=drv.probability,
                occurred_pct=round(100.0 * cnt / N, 1),
                delay_when_occurs_days=round(delay_days, 1),
                expected_delay_days=round(drv.probability * delay_days, 1),
                critical_hit_pct=round(100.0 * driver_critical[d_idx] / N, 1),
            )
        )
    driver_stats.sort(key=lambda s: abs(s.expected_delay_days), reverse=True)

    activity_stats: list[ActivityStat] = []
    if track_activities and n:
        for i in range(n):
            ci = crit[i] / N
            if i in s_d:
                mean_d = s_d[i] / N
                var_d = max(0.0, s_dd[i] / N - mean_d * mean_d)
                sd_d = math.sqrt(var_d)
                cov = s_dt[i] / N - mean_d * mean_t
                cru = cov / (sd_d * sd_t) if sd_d > 0 and sd_t > 0 else 0.0
            elif ci > 0:
                mean_d, sd_d, cru = base[i], 0.0, 0.0
            else:
                continue
            activity_stats.append(
                ActivityStat(
                    index=i,
                    criticality_pct=round(100.0 * ci, 1),
                    ssi=round(ci * sd_d / sd_t, 4) if sd_t > 0 else 0.0,
                    cruciality=round(cru, 3),
                    duration_sd_hours=round(sd_d, 2),
                    mean_duration_hours=round(mean_d, 2),
                )
            )

    return SimulationResult(
        iterations=iterations,
        calibration_offset=calibration,
        offsets_sorted=sorted(finishes),
        mean_offset=mean_t,
        sd_offset=sd_t,
        drivers=driver_stats,
        activities=activity_stats,
    )


def rank_risks(
    network: Network,
    drivers: Sequence[RiskDriver],
    *,
    iterations: int,
    hours_per_day: float,
    seed: int,
    weights: CorrelationWeights | None = None,
    target_index: Optional[int] = None,
    pct: float = 80.0,
) -> tuple[float, float, list[tuple[str, float, float]]]:
    """Hulett / 57R-09 ranking: re-simulate with each risk's probability at 0
    (common random numbers, so only that risk changes) and measure how far the
    P-value moves. Returns (P with all risks, P background only,
    [(key, ΔP working days, ΔP50 working days)] sorted by ΔP). Contributions
    are NOT additive — risks interact through the network."""

    def run(ds: Sequence[RiskDriver]) -> list[float]:
        return simulate(
            network, ds, iterations=iterations, hours_per_day=hours_per_day, seed=seed,
            weights=weights, target_index=target_index, track_activities=False,
        ).offsets_sorted

    def zeroed(skip: Optional[int]) -> list[RiskDriver]:
        out = []
        for j, d in enumerate(drivers):
            if skip is None or j == skip:
                out.append(RiskDriver(d.key, d.title, 0.0, d.impact, d.distribution, d.mode,
                                      d.activity_indices, d.is_opportunity, d._pert_table))
            else:
                out.append(d)
        return out

    all_on = run(drivers)
    p_all = percentile(all_on, pct)
    p50_all = percentile(all_on, 50)
    background = run(zeroed(None))
    p_bg = percentile(background, pct)
    ranking = []
    for j, d in enumerate(drivers):
        without = run(zeroed(j))
        ranking.append(
            (
                d.key,
                round((p_all - percentile(without, pct)) / hours_per_day, 1),
                round((p50_all - percentile(without, 50)) / hours_per_day, 1),
            )
        )
    ranking.sort(key=lambda r: abs(r[1]), reverse=True)
    return p_all, p_bg, ranking
