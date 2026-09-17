import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WbsNodeCreate(BaseModel):
    # None = new root node. Otherwise must match an existing node's wbs_id
    # within the same project (checked by the route, not here).
    parent_wbs_id: str | None = None
    wbs_short_name: str = Field(min_length=1, max_length=50)
    wbs_name: str = Field(min_length=1, max_length=255)

    @field_validator("wbs_short_name", "wbs_name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("cannot be blank")
        return v


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
    # --- hierarchy, computed by the route (nodes are returned in preorder) ---
    depth: int = 0  # 0 = root
    path_ids: list[str] = []  # root → this node, inclusive
    outline_code: str = ""  # dotted-decimal, e.g. "1.2.1" — P6 "WBS Code" column
