import json
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_CRITERIA_BYTES = 4096


class SavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    criteria: dict = Field(default_factory=dict)
    is_shared: bool = False
    filter_version: int = 1

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

    @field_validator("criteria")
    @classmethod
    def _criteria_size(cls, v: dict) -> dict:
        if len(json.dumps(v)) > _MAX_CRITERIA_BYTES:
            raise ValueError("criteria is too large")
        return v


class SavedFilterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    criteria: dict | None = None
    is_shared: bool | None = None
    filter_version: int | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

    @field_validator("criteria")
    @classmethod
    def _criteria_size(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v)) > _MAX_CRITERIA_BYTES:
            raise ValueError("criteria is too large")
        return v


class SavedFilterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    view_key: str
    name: str
    criteria: dict
    is_shared: bool
    filter_version: int
    is_owner: bool = True
    created_at: datetime
    updated_at: datetime
