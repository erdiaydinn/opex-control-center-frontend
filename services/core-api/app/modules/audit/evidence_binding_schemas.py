from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditEvidenceBindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_evidence_receipt_id: UUID
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_policy_version: str = Field(min_length=1, max_length=80)
    detector_model_ref: str = Field(min_length=1, max_length=300)
    device_id: str | None = Field(default=None, max_length=180)
