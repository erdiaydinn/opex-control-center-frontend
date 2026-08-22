from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanogramShelfScanShelfEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aisle_id: str = Field(min_length=1, max_length=120)
    module_id: str = Field(min_length=1, max_length=120)
    shelf_no: str = Field(min_length=1, max_length=120)
    source_ref: str = Field(min_length=1, max_length=500)
    coverage_complete: bool
    image_quality_score: float = Field(ge=0.0, le=1.0)
    occlusion_pct: float = Field(ge=0.0, le=100.0)

    @field_validator("aisle_id", "module_id", "shelf_no", "source_ref")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("shelf scan evidence text cannot be blank")
        return stripped


class PlanogramShelfScanObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=160)
    aisle_id: str = Field(min_length=1, max_length=120)
    module_id: str = Field(min_length=1, max_length=120)
    shelf_no: str = Field(min_length=1, max_length=120)
    facing_count: int = Field(ge=1, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str | None = Field(default=None, max_length=500)

    @field_validator("sku", "aisle_id", "module_id", "shelf_no")
    @classmethod
    def normalize_text(cls, value: str, info) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("shelf scan observation text cannot be blank")
        return stripped.upper() if info.field_name == "sku" else stripped


class PlanogramShelfScanPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_payload: dict[str, Any]
    shelves: list[PlanogramShelfScanShelfEvidence] = Field(
        min_length=1,
        max_length=2_000,
    )
    observations: list[PlanogramShelfScanObservation] = Field(
        default_factory=list,
        max_length=20_000,
    )
    min_detection_confidence: float = Field(default=0.80, ge=0.50, le=1.0)
    min_image_quality: float = Field(default=0.70, ge=0.0, le=1.0)
    max_occlusion_pct: float = Field(default=35.0, ge=0.0, le=100.0)

    @field_validator("plan_payload")
    @classmethod
    def require_plan_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise ValueError("plan_payload is required")
        return value
