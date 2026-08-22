from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.planogram.schemas import (
    PlanogramStoreScanAnnotationPreviewRequest as LegacyPlanogramStoreScanAnnotationPreviewRequest,
)


class PlanogramStoreScanUncertaintyResolution(BaseModel):
    """Fingerprint-bound human decision for one uncertain measured scan region."""

    model_config = ConfigDict(extra="forbid")

    element_id: str = Field(min_length=1, max_length=120)
    decision: Literal["confirm", "reject"]
    classified_type: Literal[
        "wall",
        "column",
        "door",
        "opening",
        "chiller",
        "freezer",
        "fixture",
    ] | None = None
    clearance_m: float = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def reject_cannot_reclassify(self) -> PlanogramStoreScanUncertaintyResolution:
        if self.decision == "reject" and self.classified_type is not None:
            raise ValueError("Rejected uncertainty cannot carry a classified_type")
        return self


class PlanogramStoreScanAnnotationPreviewRequest(
    LegacyPlanogramStoreScanAnnotationPreviewRequest
):
    """Human review plus explicit resolution of all uncertain measured regions."""

    model_config = ConfigDict(extra="forbid")

    uncertainty_resolutions: list[PlanogramStoreScanUncertaintyResolution] = Field(
        default_factory=list,
        max_length=5000,
    )

    @field_validator("uncertainty_resolutions")
    @classmethod
    def unique_uncertainty_targets(
        cls,
        value: list[PlanogramStoreScanUncertaintyResolution],
    ) -> list[PlanogramStoreScanUncertaintyResolution]:
        ids = [item.element_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate Store Scan uncertainty resolution target")
        return value
