"""Multiple float paths — P6's Schedule Options → "Calculate multiple float paths".

A float path is a chain of driving relationships ending at one chosen activity.
Path 1 is the chain that drives that activity (its longest path); path 2 is the
next-most-critical chain feeding into path 1, and so on. Planners use this to
answer "what is actually pushing THIS milestone, and what is the next thing that
will push it once I fix the first chain" — which the single project-wide critical
path in `scheduler.py` cannot answer, because it only ever ends at project
finish.

P6 offers two methods and they are genuinely different analyses, not two
rankings of the same thing:

  * Free Float (P6's default, and the one to defend a claim with) — walk back
    from the end activity along the most critical driving relationship at each
    step. Every path is a connected chain of logic.
  * Total Float — no logic walk at all: band the activities that feed the end
    activity by their total float value. Band 1 is the lowest float, band 2 the
    next, and so on. These are *bands, not chains* — the members of a band need
    not be linked to each other, and with mixed calendars a float value is not
    directly comparable between them. It is a quick "who is near-critical"
    screen. The UI says so.

This works off the stored CPM results (`activities.total_float_hours`,
`early_start`/`early_finish`, and `activity_relationships.link_type`/`lag_days`),
which come straight from P6's own scheduler on import — so no CPM re-run is
needed and the numbers a planner sees here match the numbers in P6. Running it
as a query rather than at import time is also what lets the planner change the
end activity and re-run, which is the whole workflow.

Relationship gap
----------------
"Relationship free float" is how much the predecessor could slip before it starts
moving the successor. Poko stores early dates as dates, not datetimes (the
scheduler works in datetimes; `services/xer_import.py` truncates on the way into
the table), so a gap here is measured in whole days. Pass `work_days` to measure
it in *working* days on the predecessor's own calendar — without it a Friday →
Monday link reads as two days of slack when it has none. That does not change
which predecessor is picked at a given step (for a fixed successor both measures
order the candidates the same way), but it does change the number the planner
reads, and it changes which chain branches off first, since branch points are
compared across different successors. What cannot be recovered at this layer is
sub-day precision: a link with four hours of float on an 8h calendar reads as
zero. Each step reports its own gap so the planner can see how tight the link
really is rather than having to trust the ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable, Literal

# Working days between two dates on a given calendar. `clndr_id` is the
# activity's calendar; implementations fall back to a project default.
WorkDays = Callable[[date, date, str | None], float]

Method = Literal["total_float", "free_float"]

DEFAULT_PATH_COUNT = 4
MAX_PATH_COUNT = 10
# Guards against a cycle in the relationship set (P6 won't produce one, but a
# hand-edited schedule can) and against a single path swallowing the programme.
_MAX_CHAIN = 5000


@dataclass
class PathActivity:
    """One activity on a float path, plus the relationship that drives it from
    the previous activity on that path (`link_*` is None for the first one)."""

    external_id: str
    name: str | None
    wbs_path: str | None
    status: str | None
    percent_complete: int
    early_start: date | None
    early_finish: date | None
    late_start: date | None
    late_finish: date | None
    total_float_days: float | None
    free_float_days: float | None
    is_critical: bool
    is_longest_path: bool
    link_type: str | None = None
    lag_days: int | None = None
    # Slack on the driving link, in days. 0 means the predecessor is holding
    # this activity; a larger number means the link is slack and this step was
    # the least-slack option rather than a hard driver.
    link_gap_days: float | None = None


@dataclass
class FloatPath:
    path_no: int
    activities: list[PathActivity] = field(default_factory=list)
    # The path's own float: the tightest total float on it.
    total_float_days: float | None = None
    # Where this path feeds into an earlier one, and over which link (None for
    # path 1, which ends at the chosen activity itself).
    joins_at_external_id: str | None = None
    join_link_type: str | None = None
    join_lag_days: int | None = None
    join_gap_days: float | None = None


@dataclass
class FloatPathResult:
    end_activity_external_id: str
    method: Method
    requested_paths: int
    paths: list[FloatPath] = field(default_factory=list)
    # Activities reachable as predecessors but left out because the requested
    # number of paths ran out — the planner's cue to ask for more.
    truncated: bool = False
    # How far path 1 can be pulled in before path 2 becomes the critical one.
    # Accelerating past this buys nothing, which is the number mitigation
    # decisions actually turn on and the one P6 makes you work out by hand.
    acceleration_headroom_days: float | None = None


@dataclass
class _Act:
    external_id: str
    clndr_id: str | None = None
    name: str | None = None
    wbs_path: str | None = None
    status: str | None = None
    percent_complete: int = 0
    early_start: date | None = None
    early_finish: date | None = None
    late_start: date | None = None
    late_finish: date | None = None
    total_float_hours: float | None = None
    free_float_hours: float | None = None
    is_critical: bool = False
    is_longest_path: bool = False


@dataclass
class _Rel:
    pred_external_id: str
    succ_external_id: str
    link_type: str = "FS"
    lag_days: int = 0


def _days(hours: float | None, hours_per_day: float) -> float | None:
    if hours is None:
        return None
    return round(hours / hours_per_day, 2)


def _gap(pred: _Act, succ: _Act, link_type: str, lag_days: int, work_days: WorkDays | None) -> float | None:
    """Slack on one relationship, in days. None when either end is missing the
    dates the link type needs. The `offset` is the day an FS or SF successor
    can start/finish on: the one *after* the predecessor's, not the same one."""
    lt = (link_type or "FS").upper()
    if lt == "FS":
        a, b, offset = pred.early_finish, succ.early_start, 1
    elif lt == "SS":
        a, b, offset = pred.early_start, succ.early_start, 0
    elif lt == "FF":
        a, b, offset = pred.early_finish, succ.early_finish, 0
    elif lt == "SF":
        a, b, offset = pred.early_start, succ.early_finish, 1
    else:
        return None
    if a is None or b is None:
        return None
    if work_days is not None:
        span = work_days(a, b, pred.clndr_id)
    else:
        span = float((b - a).days)
    return round(span - offset - (lag_days or 0), 2)


class _Walker:
    def __init__(self, acts: dict[str, _Act], rels: list[_Rel], work_days: WorkDays | None):
        self.acts = acts
        self.work_days = work_days
        self.pred_adj: dict[str, list[_Rel]] = {}
        for r in rels:
            if r.pred_external_id in acts and r.succ_external_id in acts:
                self.pred_adj.setdefault(r.succ_external_id, []).append(r)

    def gap(self, rel: _Rel) -> float | None:
        return _gap(
            self.acts[rel.pred_external_id],
            self.acts[rel.succ_external_id],
            rel.link_type,
            rel.lag_days,
            self.work_days,
        )

    def rank(self, rel: _Rel) -> tuple:
        """"Most critical driving relationship": tightest link first, then the
        predecessor with the least total float. Ties break on the id so a report
        a planner re-runs does not shuffle."""
        gap = self.gap(rel)
        tf = self.acts[rel.pred_external_id].total_float_hours
        return (
            float("inf") if gap is None else gap,
            float("inf") if tf is None else tf,
            rel.pred_external_id,
        )

    def candidates(self, succ_external_id: str, used: set[str]) -> list[_Rel]:
        return [r for r in self.pred_adj.get(succ_external_id, []) if r.pred_external_id not in used]

    def walk(self, start_external_id: str, used: set[str]) -> list[tuple[_Act, _Rel | None]]:
        """Follow driving predecessors back from `start_external_id`. Returns
        the chain in chronological order, each activity paired with the link
        that drives it from the one before."""
        chain: list[tuple[_Act, _Rel | None]] = [(self.acts[start_external_id], None)]
        seen = {start_external_id}
        current = start_external_id
        while len(chain) < _MAX_CHAIN:
            options = [r for r in self.candidates(current, used) if r.pred_external_id not in seen]
            if not options:
                break
            best = min(options, key=self.rank)
            chain.append((self.acts[best.pred_external_id], best))
            seen.add(best.pred_external_id)
            current = best.pred_external_id
        chain.reverse()
        return chain


def compute_float_paths(
    activities: Iterable[dict],
    relationships: Iterable[dict],
    end_external_id: str,
    *,
    method: Method = "free_float",
    path_count: int = DEFAULT_PATH_COUNT,
    hours_per_day: float = 8.0,
    work_days: WorkDays | None = None,
    exclude_completed: bool = True,
) -> FloatPathResult:
    acts = {
        a["external_id"]: _Act(
            external_id=a["external_id"],
            clndr_id=a.get("clndr_id"),
            name=a.get("name"),
            wbs_path=a.get("wbs_path"),
            status=a.get("status"),
            percent_complete=int(a.get("percent_complete") or 0),
            early_start=a.get("early_start"),
            early_finish=a.get("early_finish"),
            late_start=a.get("late_start"),
            late_finish=a.get("late_finish"),
            total_float_hours=a.get("total_float_hours"),
            free_float_hours=a.get("free_float_hours"),
            is_critical=bool(a.get("is_critical")),
            is_longest_path=bool(a.get("is_longest_path")),
        )
        for a in activities
        if a.get("external_id")
    }
    if end_external_id not in acts:
        raise KeyError(end_external_id)

    rels = [
        _Rel(
            pred_external_id=r["pred_external_id"],
            succ_external_id=r["succ_external_id"],
            link_type=(r.get("link_type") or "FS"),
            lag_days=int(r.get("lag_days") or 0),
        )
        for r in relationships
    ]

    path_count = max(1, min(int(path_count), MAX_PATH_COUNT))
    walker = _Walker(acts, rels, work_days)

    # P6 leaves completed work out of a float path: it cannot drive anything any
    # more. The end activity itself always stays, or there is nothing to analyse.
    if exclude_completed:
        done = {
            eid
            for eid, a in acts.items()
            if eid != end_external_id and (a.status == "complete" or a.percent_complete >= 100)
        }
    else:
        done = set()

    if method == "total_float":
        return _float_bands(walker, acts, end_external_id, path_count, hours_per_day, done)

    used: set[str] = set(done)
    paths: list[FloatPath] = []
    # Every activity already on a path is a potential branch point for the next
    # one, so the next path is found by looking for the tightest relationship
    # into any of these from a predecessor nothing has claimed yet.
    assigned: list[str] = []

    for path_no in range(1, path_count + 1):
        join: _Rel | None = None
        if path_no == 1:
            chain = walker.walk(end_external_id, used)
        else:
            branches = [rel for succ in assigned for rel in walker.candidates(succ, used)]
            if not branches:
                break
            join = min(branches, key=walker.rank)
            chain = walker.walk(join.pred_external_id, used)

        if not chain:
            break

        # `chain` runs earliest-first and pairs each activity with the link
        # OUT of it. A planner reads the path downwards, so each row shows the
        # link that drove it IN from the row above — shift by one.
        entries: list[PathActivity] = []
        for i, (act, _out) in enumerate(chain):
            link = chain[i - 1][1] if i > 0 else None
            entries.append(
                PathActivity(
                    external_id=act.external_id,
                    name=act.name,
                    wbs_path=act.wbs_path,
                    status=act.status,
                    percent_complete=act.percent_complete,
                    early_start=act.early_start,
                    early_finish=act.early_finish,
                    late_start=act.late_start,
                    late_finish=act.late_finish,
                    total_float_days=_days(act.total_float_hours, hours_per_day),
                    free_float_days=_days(act.free_float_hours, hours_per_day),
                    is_critical=act.is_critical,
                    is_longest_path=act.is_longest_path,
                    link_type=link.link_type if link else None,
                    lag_days=link.lag_days if link else None,
                    link_gap_days=(
                        walker.gap(link) if link else None
                    ),
                )
            )

        floats = [e.total_float_days for e in entries if e.total_float_days is not None]
        paths.append(
            FloatPath(
                path_no=path_no,
                activities=entries,
                total_float_days=min(floats) if floats else None,
                joins_at_external_id=join.succ_external_id if join else None,
                join_link_type=join.link_type if join else None,
                join_lag_days=join.lag_days if join else None,
                join_gap_days=walker.gap(join) if join else None,
            )
        )
        for e in entries:
            used.add(e.external_id)
            assigned.append(e.external_id)

    truncated = any(walker.candidates(succ, used) for succ in assigned)
    return FloatPathResult(
        end_activity_external_id=end_external_id,
        method=method,
        requested_paths=path_count,
        paths=paths,
        truncated=truncated,
        acceleration_headroom_days=_headroom(paths),
    )


def _headroom(paths: list[FloatPath]) -> float | None:
    """How far path 1 can be pulled in before path 2 takes over as critical."""
    if len(paths) < 2:
        return None
    first, second = paths[0].total_float_days, paths[1].total_float_days
    if first is None or second is None:
        return None
    return round(second - first, 2)


def _float_bands(
    walker: _Walker,
    acts: dict[str, _Act],
    end_external_id: str,
    band_count: int,
    hours_per_day: float,
    excluded: set[str],
) -> FloatPathResult:
    """P6's Total Float method. Not a logic walk at all: take everything that
    feeds the end activity and band it by total float, lowest first. Members of
    a band need not be linked to one another — this answers "who is
    near-critical", not "what drives what"."""
    reachable: set[str] = {end_external_id}
    stack = [end_external_id]
    while stack:
        current = stack.pop()
        for rel in walker.pred_adj.get(current, []):
            pred = rel.pred_external_id
            if pred not in reachable and pred not in excluded:
                reachable.add(pred)
                stack.append(pred)

    by_float: dict[float, list[_Act]] = {}
    for eid in reachable:
        act = acts[eid]
        tf = _days(act.total_float_hours, hours_per_day)
        if tf is None:
            continue
        by_float.setdefault(tf, []).append(act)

    bands = sorted(by_float)
    paths: list[FloatPath] = []
    for band_no, tf in enumerate(bands[:band_count], start=1):
        members = sorted(
            by_float[tf],
            key=lambda a: (a.early_start or date.max, a.external_id),
        )
        paths.append(
            FloatPath(
                path_no=band_no,
                total_float_days=tf,
                activities=[
                    PathActivity(
                        external_id=a.external_id,
                        name=a.name,
                        wbs_path=a.wbs_path,
                        status=a.status,
                        percent_complete=a.percent_complete,
                        early_start=a.early_start,
                        early_finish=a.early_finish,
                        late_start=a.late_start,
                        late_finish=a.late_finish,
                        total_float_days=tf,
                        free_float_days=_days(a.free_float_hours, hours_per_day),
                        is_critical=a.is_critical,
                        is_longest_path=a.is_longest_path,
                    )
                    for a in members
                ],
            )
        )

    return FloatPathResult(
        end_activity_external_id=end_external_id,
        method="total_float",
        requested_paths=band_count,
        paths=paths,
        truncated=len(bands) > band_count,
        acceleration_headroom_days=_headroom(paths),
    )
