import sys

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

_auth = f":{settings.redis_password}@" if settings.redis_password else ""
_broker_url = f"redis://{_auth}{settings.redis_host}:{settings.redis_port}/0"

celery_app = Celery("poko", broker=_broker_url, backend=_broker_url)
celery_app.conf.task_default_queue = "poko"

# Under pytest, run tasks synchronously in-process with no broker/worker involved
# at all (the standard Celery testing pattern) — the alternative is every test
# that logs in or sends an invite needing a live Redis + Postgres to succeed.
# Checked via sys.modules, not the PYTEST_CURRENT_TEST env var: that var is only
# set while an individual test is executing, not during collection — and this
# module is imported once, at collection time, before any test has started.
celery_app.conf.task_always_eager = "pytest" in sys.modules
celery_app.conf.task_eager_propagates = False

# Phase 2 will register the P6 import/export and Monte Carlo/EVM analysis tasks here.
from app.worker import tasks  # noqa: E402,F401
