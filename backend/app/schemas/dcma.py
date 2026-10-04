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
    denominator: int = 0
    basis: str = "activities"


class DcmaReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    computed_at: str
    total_activities: int
    in_scope: int
    overall_score: float
    overall_status: str
    checks: list[DcmaCheckResultOut]
    # The targets this report was measured against, DCMA's own, and which of
    # them the project changed.
    thresholds: dict[str, float] = {}
    default_thresholds: dict[str, float] = {}
    customized: list[str] = []
    can_edit_thresholds: bool = False
