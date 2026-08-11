import logging
import uuid

from app.core.config import get_settings
from app.core.notifications import send_invite_email as _send_invite_email
from app.worker.celery_app import celery_app

logger = logging.getLogger("poko.worker")
settings = get_settings()


@celery_app.task(name="poko.ping")
def ping() -> str:
    """Placeholder task proving the worker/broker wiring works end-to-end."""
    return "pong"


@celery_app.task(name="poko.send_invite_email")
def send_invite_email(
    to_email: str, raw_token: str, role: str, tenant_name: str | None = None
) -> None:
    """Takes the raw token as an argument rather than looking an Invite up by id
    — only the token's hash is ever persisted, so the raw value only exists for
    the moment `create_invite` generates it and hands it straight to this task."""
    invite_url = f"{settings.frontend_url}/invite/{raw_token}"
    _send_invite_email(to_email=to_email, invite_url=invite_url, role=role, tenant_name=tenant_name)


@celery_app.task(name="poko.write_audit_log")
def write_audit_log(
    action: str,
    tenant_id: str | None,
    actor_user_id: str | None,
    target_type: str | None = None,
    target_id: str | None = None,
    event_metadata: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Async, best-effort by design (per the task's own "shouldn't block the
    request" requirement): a failure here is logged, never raised back at
    whatever request triggered it. The one place audit logging must not be
    best-effort — the platform support-access path — writes synchronously and
    is not this task; see app/services/audit.py:log_sync.
    """
    # Imported lazily so this module (and Celery task registration) doesn't
    # require a live DB connection just to import.
    from app.db.session import BypassSessionLocal, SessionLocal, set_rls_context
    from app.models.audit_log import AuditLog

    db = BypassSessionLocal() if tenant_id is None else SessionLocal()
    try:
        if tenant_id is not None:
            set_rls_context(db, uuid.UUID(tenant_id))
        db.add(
            AuditLog(
                tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
                actor_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
                action=action,
                target_type=target_type,
                target_id=uuid.UUID(target_id) if target_id else None,
                event_metadata=event_metadata or {},
                ip_address=ip_address,
            )
        )
        db.commit()
    except Exception:
        logger.exception("Failed to write audit log entry action=%s", action)
    finally:
        db.close()
