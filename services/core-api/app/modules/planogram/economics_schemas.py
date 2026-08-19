from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.planogram.schemas import PlanogramPreviewRequest


class AttestedRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: float = Field(gt=0)
    base: float = Field(gt=0)
    high: float = Field(gt=0)
    source_ref: str = Field(min_length=3, max_length=500)
    attested: bool

    @model_validator(mode="after")
    def ordered_range(self) -> AttestedRange:
        if not self.low <= self.base <= self.high:
            raise ValueError("Economics range must satisfy low <= base <= high")
        return self


class AttestedCapexItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=160)
    amount: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    source_ref: str = Field(min_length=3, max_length=500)
    attested: bool


class PlanogramEconomicsAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    orders_per_day: AttestedRange
    operating_days_per_year: AttestedRange
    effective_seconds_per_meter: AttestedRange
    loaded_labor_cost_per_hour: AttestedRange
    capex_items: list[AttestedCapexItem] = Field(min_length=1, max_length=100)


class PlanogramPhysicalEconomicsPreviewRequest(PlanogramPreviewRequest):
    model_config = ConfigDict(extra="forbid")

    economics: PlanogramEconomicsAssumptions


class PlanogramPhysicalCandidateEconomicsPreviewRequest(
    PlanogramPhysicalEconomicsPreviewRequest
):
    model_config = ConfigDict(extra="forbid")

    layout_fingerprint: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
