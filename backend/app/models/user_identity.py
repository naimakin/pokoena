import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdentityProvider(str, enum.Enum):
    password = "password"
    google = "google"
    microsoft_entra = "microsoft_entra"


class UserIdentity(Base):
    """Links a User to an auth provider. Only `password` is populated at MVP;
    this table exists so Google Workspace / Microsoft Entra OIDC can be added
    later by inserting rows here, without altering the User table."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject_id", name="uq_user_identity_provider_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[IdentityProvider] = mapped_column(
        SAEnum(IdentityProvider, name="identity_provider"), nullable=False
    )
    provider_subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
