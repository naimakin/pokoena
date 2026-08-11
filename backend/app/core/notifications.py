import logging

logger = logging.getLogger("poko.notifications")


def send_reminder_email(to_email: str, subject: str, body: str) -> None:
    # Phase 2 TODO: wire up a real transactional email provider (e.g. Postmark/SES).
    # Logging keeps the reminder workflow fully wired end-to-end until then.
    logger.info("EMAIL to=%s subject=%s body=%s", to_email, subject, body)


def send_invite_email(to_email: str, invite_url: str, role: str, tenant_name: str | None) -> None:
    # Same "log until Phase 2 wires a real provider" pattern as send_reminder_email.
    # The raw token only ever exists in this URL — it's never persisted (only its
    # hash is), so this call is the one and only place it's observable.
    subject = f"You're invited to POKO{f' — {tenant_name}' if tenant_name else ''}"
    body = f"You've been invited as {role}. Set your password: {invite_url} (expires in 72 hours)"
    logger.info("EMAIL to=%s subject=%s body=%s", to_email, subject, body)
