import enum
import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinkType(str, enum.Enum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


class ActivityRelationship(Base):
    __tablename__ = "activity_relationships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    predecessor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), nullable=False)
    successor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), nullable=False)
    link_type: Mapped[LinkType] = mapped_column(
        SAEnum(LinkType, name="link_type"), nullable=False, default=LinkType.FS
    )
    lag_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
