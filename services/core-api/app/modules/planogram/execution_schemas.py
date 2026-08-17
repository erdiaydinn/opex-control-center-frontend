from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanogramPlanDraftRequest(StrictModel):
    store_dna_version_id: UUID
    store_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    source: Literal["optimizer_preview", "manual_import"] = "optimizer_preview"
    plan_payload: dict[str, Any]
    optimizer_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class PlanogramPlanEditRequest(StrictModel):
    plan_payload: dict[str, Any]
    optimizer_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class PlanogramPlanRejectRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class PlanogramExecutionAssignmentRequest(StrictModel):
    plan_version_id: UUID
    effective_from: datetime
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: datetime | None, info):
        effective_from = info.data.get("effective_from")
        if value is not None and effective_from is not None and value < effective_from:
            raise ValueError("due_at must not be earlier than effective_from")
        return value


class PlanogramComplianceConsumeRequest(StrictModel):
    field_promotion_id: UUID
