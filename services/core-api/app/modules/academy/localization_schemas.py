from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

TranslationMethod = Literal["human", "machine_assisted", "machine_draft"]
TranslationDecision = Literal["approved", "rejected"]


class LocaleSettingUpdateRequest(BaseModel):
    enabled: bool = True
    required: bool = False
    is_default: bool = False
    allow_machine_draft: bool = False

    @model_validator(mode="after")
    def validate_enabled_dependencies(self) -> "LocaleSettingUpdateRequest":
        if self.required and not self.enabled:
            raise ValueError("required locale must be enabled")
        if self.is_default and not self.enabled:
            raise ValueError("default locale must be enabled")
        return self


class TranslationLineageCreateRequest(BaseModel):
    source_version_id: UUID
    target_version_id: UUID
    translation_method: TranslationMethod = "human"

    @model_validator(mode="after")
    def validate_distinct_versions(self) -> "TranslationLineageCreateRequest":
        if self.source_version_id == self.target_version_id:
            raise ValueError("source and target versions must differ")
        return self


class TranslationReviewRequest(BaseModel):
    decision: TranslationDecision
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "TranslationReviewRequest":
        if self.decision == "rejected" and not str(self.reason or "").strip():
            raise ValueError("rejection requires a reason")
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        return self
