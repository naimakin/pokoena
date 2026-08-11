import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.worker.tasks import write_audit_log


def log(
    action: str,
    tenant_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    event_metadata: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Fire-and-forget: enqueues the write via Celery so audit logging never
    adds latency to the request it's describing. Used for logins, invite
    accept/create, role changes, and ordinary cross-tenant/cross-scope denials.
    """
    write_audit_log.delay(
        action=action,
        tenant_id=str(tenant_id) if tenant_id else None,
        actor_user_id=str(actor_user_id) if actor_user_id else None,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        event_metadata=event_metadata or {},
        ip_address=ip_address,
    )


def log_sync(
    db: Session,
    action: str,
    tenant_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    event_metadata: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Synchronous, same-transaction write for the one case where "logged" has
    to be non-negotiable and atomic with the privileged action rather than
    best-effort: the platform support-access path (see app/deps.py). Not used
    anywhere else — everything else goes through `log()` above.
    """
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            event_metadata=event_metadata or {},
            ip_address=ip_address,
        )
    )
