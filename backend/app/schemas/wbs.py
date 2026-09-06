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
    # activities whose TASK.wbs_id points straight at this node
    direct_activity_count: int = 0
    # direct_activity_count for this node plus every descendant (P6's
    # "Total Activities" rollup column)
    total_activity_count: int = 0
