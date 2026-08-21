from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class BadgeDefinitionCreateRequest(BaseModel):
    badge_key: str = Field(min_length=2, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    version_number: int = Field(ge=1, le=100000)
    skill_id: UUID
    minimum_level: int = Field(ge=1, le=5)
    title_i18n: dict[str, str] = Field(min_length=1)
    description_i18n: dict[str, str] = Field(default_factory=dict)
    criteria_i18n: dict[str, str] = Field(default_factory=dict)
    validity_days: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def normalize_i18n(self) -> "BadgeDefinitionCreateRequest":
        self.title_i18n = {
            str(locale).strip(): str(value).strip()
            for locale, value in self.title_i18n.items()
            if str(locale).strip() and str(value).strip()
        }
        self.description_i18n = {
            str(locale).strip(): str(value).strip()
            for locale, value in self.description_i18n.items()
            if str(locale).strip() and str(value).strip()
        }
        self.criteria_i18n = {
            str(locale).strip(): str(value).strip()
            for locale, value in self.criteria_i18n.items()
            if str(locale).strip() and str(value).strip()
        }
        if not self.title_i18n:
            raise ValueError("badge title must contain at least one localized value")
        return self


class BadgeRetirementRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def normalize_reason(self) -> "BadgeRetirementRequest":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("retirement reason is required")
        return self


class BadgeAwardIssueRequest(BaseModel):
    badge_definition_id: UUID
    skill_evidence_id: UUID


class BadgeRevocationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def normalize_reason(self) -> "BadgeRevocationRequest":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("revocation reason is required")
        return self
