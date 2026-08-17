import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActivityEvmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: uuid.UUID
    external_id: str
    name: str
    status_code: str | None
    percent_complete: int

    bac: float
    pv: float | None
    ev: float
    ac: float

    cpi: float | None
    spi: float | None
    sv: float | None
    cv: float

    eac_cpi: float | None
    eac_pf: float | None
    vac: float | None

    remaining_manhour: float
    remaining_qty: float


class QuickEvmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data_date: datetime | None

    bac: float
    pv: float | None
    ev: float
    ac: float

    cpi: float | None
    spi: float | None
    sv: float | None
    cv: float

    eac_cpi: float | None
    eac_pf: float | None
    vac: float | None

    activity_results: list[ActivityEvmOut]
