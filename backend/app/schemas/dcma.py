from pydantic import BaseModel, ConfigDict


class DcmaCheckResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    value: float
    threshold: float
    pct: float
    unit: str
    details: list[str]


class DcmaReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    computed_at: str
    total_activities: int
    in_scope: int
    overall_score: float
    overall_status: str
    checks: list[DcmaCheckResultOut]
