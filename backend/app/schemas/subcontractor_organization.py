import uuid

from pydantic import BaseModel, ConfigDict


class SubcontractorOrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    discipline: str


class SubcontractorOrgCreate(BaseModel):
    name: str
    discipline: str
