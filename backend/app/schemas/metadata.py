import uuid

from pydantic import BaseModel, ConfigDict, Field


class CalendarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clndr_id: str
    name: str
    hours_per_day: float


class CalendarPatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rsrc_id: str
    name: str
    short_name: str | None
    rsrc_type: str
    unit_id: str | None
    curr_id: str | None


class ResourcePatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    short_name: str | None = Field(default=None, max_length=120)
    unit_id: str | None = Field(default=None, max_length=50)
    curr_id: str | None = Field(default=None, max_length=50)


class ActivityCodeValuePatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    short_name: str | None = Field(default=None, max_length=120)
