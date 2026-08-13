import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.password_reset import PasswordReset
from app.models.user import User

RESET_EXPIRY = timedelta(hours=24)


class PasswordResetError(Exception):
    """Invalid, expired, or already-used reset token."""


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _as_aware_utc(dt: datetime) -> datetime:
    """See services/invites.py's identical helper — SQLite (pytest) hands
    back naive datetimes even though every value is written as UTC-aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def create_password_reset(db: Session, user_id: uuid.UUID, created_by_user_id: uuid.UUID) -> tuple[PasswordReset, str]:
    """Returns `(reset, reset_url)` — same "hand the raw link straight back to
    whoever created it" pattern as services/invites.create_invite, and for the
    same reason: no transactional email provider is wired up yet, so a
    delivered email isn't something the creator can rely on."""
    raw_token = secrets.token_urlsafe(32)
    reset = PasswordReset(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        created_by_user_id=created_by_user_id,
        expires_at=datetime.now(timezone.utc) + RESET_EXPIRY,
    )
    db.add(reset)
    db.commit()
    db.refresh(reset)
    reset_url = f"{get_settings().frontend_url}/reset-password/{raw_token}"
    return reset, reset_url


def get_reset_preview(db: Session, raw_token: str) -> User:
    """Used by the public `GET /auth/reset-password/{token}` preview."""
    reset = db.query(PasswordReset).filter(PasswordReset.token_hash == _hash_token(raw_token)).first()
    if reset is None:
        raise PasswordResetError("Invalid reset link")
    if reset.used_at is not None:
        raise PasswordResetError("This reset link has already been used")
    if _as_aware_utc(reset.expires_at) < datetime.now(timezone.utc):
        raise PasswordResetError("This reset link has expired")
    user = db.get(User, reset.user_id)
    if user is None:
        raise PasswordResetError("Invalid reset link")
    return user


def apply_password_reset(db: Session, raw_token: str, new_password: str) -> User:
    token_hash = _hash_token(raw_token)
    query = db.query(PasswordReset).filter(PasswordReset.token_hash == token_hash)
    # No RLS on password_resets (see the model), so — unlike invites — no
    # BYPASSRLS bootstrap step is needed here to make this lookup or its lock
    # possible; the ordinary session already sees every row.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    reset = query.first()
    if reset is None:
        raise PasswordResetError("Invalid reset link")
    if reset.used_at is not None:
        raise PasswordResetError("This reset link has already been used")
    if _as_aware_utc(reset.expires_at) < datetime.now(timezone.utc):
        raise PasswordResetError("This reset link has expired")

    user = db.get(User, reset.user_id)
    if user is None:
        raise PasswordResetError("Invalid reset link")

    user.hashed_password = hash_password(new_password)
    user.is_active = True
    reset.used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user
