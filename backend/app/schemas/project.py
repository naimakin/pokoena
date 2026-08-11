import uuid

from pydantic import BaseModel, ConfigDict


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str


class ProjectCreate(BaseModel):
    name: str
    code: str


class ProjectScopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    subcontractor_org_id: uuid.UUID | None
    name: str
    discipline: str


class ProjectScopeCreate(BaseModel):
    name: str
    discipline: str
    subcontractor_org_id: uuid.UUID | None = None
