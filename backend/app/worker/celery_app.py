from celery import Celery

from app.core.config import get_settings

settings = get_settings()

_auth = f":{settings.redis_password}@" if settings.redis_password else ""
_broker_url = f"redis://{_auth}{settings.redis_host}:{settings.redis_port}/0"

celery_app = Celery("poko", broker=_broker_url, backend=_broker_url)
celery_app.conf.task_default_queue = "poko"

# Phase 2 will register the P6 import/export and Monte Carlo/EVM analysis tasks here.
from app.worker import tasks  # noqa: E402,F401
