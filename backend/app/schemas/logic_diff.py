from pydantic import BaseModel, ConfigDict


class LogicDiffChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pred_external_id: str
    pred_name: str
    succ_external_id: str
    succ_name: str
    change_type: str
    changes: list[str]
    old_link_type: str | None
    new_link_type: str | None
    old_lag_hours: float | None
    new_lag_hours: float | None
    pred_was_critical: bool
    succ_was_critical: bool


class LogicDiffSummaryOut(BaseModel):
    added: int
    removed: int
    modified: int
    total: int


class LogicDiffReportOut(BaseModel):
    from_import_id: str
    to_import_id: str
    summary: LogicDiffSummaryOut
    changes: list[LogicDiffChangeOut]
