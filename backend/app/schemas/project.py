import uuid

from pydantic import BaseModel, ConfigDict, Field


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str


class ProjectCreate(BaseModel):
    name: str
    code: str


class ProjectUpdate(BaseModel):
    name: str | None = None
    code: str | None = None


class ProjectScopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    subcontractor_org_id: uuid.UUID | None
    name: str
    discipline: str
    # The scope's rule (services/scope_rules.py): P6 WBS ids and activity code ids.
    wbs_ids: list[str] = []
    code_value_ids: list[str] = []
    # Activities currently in the scope, and the subcontractors assigned to it.
    activity_count: int = 0
    member_count: int = 0


class ProjectScopeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    discipline: str = Field(default="General", min_length=1, max_length=120)
    subcontractor_org_id: uuid.UUID | None = None
    wbs_ids: list[str] = []
    code_value_ids: list[str] = []


class ProjectScopeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    discipline: str | None = Field(default=None, min_length=1, max_length=120)
    subcontractor_org_id: uuid.UUID | None = None
    wbs_ids: list[str] | None = None
    code_value_ids: list[str] | None = None


class ScopePreviewIn(BaseModel):
    wbs_ids: list[str] = []
    code_value_ids: list[str] = []


class ScopePreviewActivity(BaseModel):
    external_id: str
    name: str
    wbs_path: str | None


class ScopePreviewOut(BaseModel):
    """What a rule selects: the total, a sample, and how many of those an
    older scope already holds (an activity belongs to one scope — the oldest)."""

    count: int
    claimed_elsewhere: int
    sample: list[ScopePreviewActivity]
