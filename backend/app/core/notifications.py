import logging

logger = logging.getLogger("poko.notifications")


def send_reminder_email(to_email: str, subject: str, body: str) -> None:
    # Phase 2 TODO: wire up a real transactional email provider (e.g. Postmark/SES).
    # Logging keeps the reminder workflow fully wired end-to-end until then.
    logger.info("EMAIL to=%s subject=%s body=%s", to_email, subject, body)
