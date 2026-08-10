from app.worker.celery_app import celery_app


@celery_app.task(name="poko.ping")
def ping() -> str:
    """Placeholder task proving the worker/broker wiring works end-to-end."""
    return "pong"
