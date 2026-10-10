"""Result cache for the heavy read endpoints (Dashboard, Portfolio).

Those endpoints rebuild the same answer from thousands of rows on every page
load, while the rows only change when someone imports a schedule, locks a
baseline, records progress, edits a risk… So each response is stored in Redis
under a key that carries the *data version* of what it was built from:

    poko:c:<name>:<scope…>:<global ver>.<tenant ver>.<project ver>

and any committed write bumps the version, so the next read misses and
recomputes — no TTL guesswork, no stale numbers after an import.

Versions are bumped by SQLAlchemy session events, for every model at once:
  - after_flush collects what the flush touched: a row with `project_id` bumps
    that project, a project-less tenant row (scope submissions, subcontractor
    orgs, roles…) bumps its tenant, a `projects` row bumps itself;
  - do_orm_execute catches bulk DML (query.delete(), insert().values(), …),
    which never passes through the flush — those bump the global version
    (they're the import / rebuild paths, so rare);
  - after_commit applies the bumps (never before: a reader must not cache old
    rows under a new version), after_rollback drops them.
Tables that never feed a cached answer (audit log, personal pins / notes,
saved filters…) are ignored so they don't throw the cache away.

Versions are random tokens, not counters: the Redis box runs allkeys-lru, so a
version key can be evicted. A missing version is re-created as a fresh token,
which can only cause a miss — never a hit on an older entry.

Redis being down is never an error: the endpoint just computes as before.
The `today`-relative bits (overdue counts, deadlines) are why entries also
expire after CACHE_TTL.
"""

from __future__ import annotations

import json
import logging
import uuid
from itertools import chain
from typing import Any, Callable, Iterable

import redis
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session

from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

CACHE_TTL = 15 * 60
_PREFIX = "poko"
_PENDING = "poko_cache_bumps"

# Writes to these never change a cached answer.
_IGNORED_TABLES = {
    "audit_logs",
    "dashboard_layouts",
    "activity_pins",
    "personal_notes",
    "saved_activity_filters",
    "report_formats",
    "mentions",
}


def _client() -> redis.Redis:
    """Overridden by the test suite with a fakeredis instance."""
    return get_redis()


def _vkey(scope: str) -> str:
    return f"{_PREFIX}:v:{scope}"


# --- invalidation ---------------------------------------------------------------


def _scopes_of(obj: Any) -> Iterable[str]:
    table = getattr(obj, "__tablename__", None)
    if table is None or table in _IGNORED_TABLES:
        return ()
    if table == "projects":
        return (f"p:{obj.id}",)
    project_id = getattr(obj, "project_id", None)
    if project_id is not None:
        return (f"p:{project_id}",)
    tenant_id = getattr(obj, "tenant_id", None)
    if tenant_id is not None:
        return (f"t:{tenant_id}",)
    return ()


@event.listens_for(Session, "after_flush")
def _collect_flush(session: Session, _ctx) -> None:
    pending = session.info.setdefault(_PENDING, set())
    for obj in chain(session.new, session.dirty, session.deleted):
        pending.update(_scopes_of(obj))


@event.listens_for(Session, "do_orm_execute")
def _collect_bulk(state: ORMExecuteState) -> None:
    if state.is_insert or state.is_update or state.is_delete:
        state.session.info.setdefault(_PENDING, set()).add("g")


@event.listens_for(Session, "after_commit")
def _apply(session: Session) -> None:
    scopes = session.info.pop(_PENDING, None)
    if scopes:
        bump(*scopes)


@event.listens_for(Session, "after_rollback")
def _discard(session: Session) -> None:
    session.info.pop(_PENDING, None)


def bump(*scopes: str) -> None:
    """New version for each scope ("g", "t:<tenant>", "p:<project>")."""
    try:
        pipe = _client().pipeline()
        for scope in scopes:
            pipe.set(_vkey(scope), uuid.uuid4().hex)
        pipe.execute()
    except redis.RedisError as exc:  # pragma: no cover - Redis down
        log.warning("cache bump failed: %s", exc)


# --- reads --------------------------------------------------------------------------


def _versions(r: redis.Redis, scopes: list[str]) -> list[str]:
    keys = [_vkey(s) for s in scopes]
    values = r.mget(keys)
    missing = [k for k, v in zip(keys, values) if v is None]
    if missing:
        pipe = r.pipeline()
        for k in missing:
            pipe.set(k, uuid.uuid4().hex, nx=True)
        pipe.execute()
        values = r.mget(keys)
    return [v or "x" for v in values]


def _dump(result: Any) -> str:
    if isinstance(result, BaseModel):
        return result.model_dump_json()
    return json.dumps(jsonable_encoder(result))


def project_scopes(tenant_id: Any, *project_ids: Any) -> list[str]:
    """What an answer about these projects depends on."""
    return ["g", f"t:{tenant_id}", *(f"p:{pid}" for pid in project_ids)]


def cached_json(name: str, *, scopes: list[str], key: Iterable[Any], compute: Callable[[], Any]) -> Any:
    """`compute()`'s result as a JSON Response, from Redis while none of
    `scopes` has changed since it was stored. `key` names the answer (project
    id, user id for answers that depend on who asks…). Call it only after the
    route's access checks — the cache is never a security boundary itself."""
    try:
        r = _client()
        versions = _versions(r, scopes)
        cache_key = f"{_PREFIX}:c:{name}:{':'.join(map(str, key))}:{'.'.join(versions)}"
        hit = r.get(cache_key)
        if hit is not None:
            return Response(hit, media_type="application/json")
    except redis.RedisError as exc:
        log.warning("cache read failed: %s", exc)
        return compute()

    body = _dump(compute())
    try:
        r.set(cache_key, body, ex=CACHE_TTL)
    except redis.RedisError as exc:  # pragma: no cover - Redis down
        log.warning("cache write failed: %s", exc)
    return Response(body, media_type="application/json")
