from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.planogram.schemas import PlanogramOrderBasket


class PlanogramBlindCandidate(BaseModel):
    """Unlabelled candidate plan; caller identity is deliberately excluded."""

    model_config = ConfigDict(extra="forbid")

    planogram: dict[str, Any]

    @field_validator("planogram")
    @classmethod
    def validate_planogram(cls, value: dict[str, Any]) -> dict[str, Any]:
        aisles = value.get("aisles")
        if not isinstance(aisles, list) or not aisles:
            raise ValueError("candidate planogram requires at least one aisle")
        if len(aisles) > 2_000:
            raise ValueError("candidate aisle limit exceeded")
        return value


class PlanogramBlindBenchmarkRequest(BaseModel):
    """Same-evidence A/B request with no expert/AI identity fields."""

    model_config = ConfigDict(extra="forbid")

    products: list[dict[str, Any]] = Field(min_length=1, max_length=20_000)
    layout: dict[str, Any]
    store_dna: dict[str, Any]
    order_baskets: list[PlanogramOrderBasket] = Field(min_length=1, max_length=5_000)
    candidate_a: PlanogramBlindCandidate
    candidate_b: PlanogramBlindCandidate

    @field_validator("layout", "store_dna")
    @classmethod
    def validate_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise ValueError("measured benchmark evidence object is required")
        return value
