import uuid

from pydantic import BaseModel, ConfigDict


class ActivityCodeTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actv_code_type_id: str
    name: str


class ActivityCodeValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code_type_id: uuid.UUID
    actv_code_id: str
    name: str
    short_name: str | None
    parent_actv_code_id: str | None
    seq_num: int | None


class ActivityCodesOut(BaseModel):
    code_types: list[ActivityCodeTypeOut]
    code_values: list[ActivityCodeValueOut]
    # code_value_id -> the activities carrying that code (TASKACTV). Sent with
    # the catalogue rather than as a second round-trip because every consumer
    # (Planning > Schedule's code filter) needs both together to show
    # "<code> (~N activities)" and then filter client-side without re-querying.
    assignments: dict[str, list[str]] = {}
