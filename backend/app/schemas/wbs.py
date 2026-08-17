import uuid

from pydantic import BaseModel, ConfigDict


class WbsNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wbs_id: str
    parent_wbs_id: str | None
    wbs_short_name: str
    wbs_name: str
    seq_num: int | None
