from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

SUPPORTED_LOCALES = frozenset({"tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"})


class GlossaryStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"


class GlossaryAliasKind(StrEnum):
    SYNONYM = "synonym"
    ACRONYM = "acronym"


class GlossaryRelationKind(StrEnum):
    PARENT = "parent"
    RELATED = "related"


class GlossaryScope(BaseModel):
    tenant_id: str = Field(min_length=1)
    country: str | None = None
    region: str | None = None
    business_unit: str | None = None
    domain: str | None = None


class LocalizedText(BaseModel):
    values: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_values(self) -> "LocalizedText":
        unknown = set(self.values) - SUPPORTED_LOCALES
        if unknown:
            raise ValueError(f"unsupported glossary locales: {', '.join(sorted(unknown))}")
        if any(not value.strip() for value in self.values.values()):
            raise ValueError("localized glossary values must not be blank")
        return self


class GlossaryAliasBinding(BaseModel):
    kind: GlossaryAliasKind
    value: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_value(self) -> "GlossaryAliasBinding":
        if not self.value.strip():
            raise ValueError("glossary alias binding must not be blank")
        return self


class GlossaryConceptRelation(BaseModel):
    kind: GlossaryRelationKind
    target_concept_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "GlossaryConceptRelation":
        if not self.target_concept_id.strip():
            raise ValueError("glossary concept relation target must not be blank")
        return self


class GlossaryTerm(BaseModel):
    concept_id: str = Field(min_length=1)
    canonical_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    scope: GlossaryScope
    status: GlossaryStatus
    version: int = Field(ge=1)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    display_name: LocalizedText
    short_definition: LocalizedText
    detailed_definition: LocalizedText | None = None
    aliases: list[str] = Field(default_factory=list)
    alias_bindings: list[GlossaryAliasBinding] = Field(default_factory=list)
    formula: str | None = None
    unit: str | None = None
    data_source_refs: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    concept_relations: list[GlossaryConceptRelation] = Field(default_factory=list)
    owner: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_effective_state(self) -> "GlossaryTerm":
        if self.status == GlossaryStatus.EFFECTIVE and self.effective_from is None:
            raise ValueError("effective glossary terms require effective_from")
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class GlossaryAmbiguityCandidate(BaseModel):
    concept_id: str
    canonical_key: str
    display_name: str
    scope: GlossaryScope
    version: int


class GlossaryAnswer(BaseModel):
    concept_id: str
    canonical_key: str
    locale: str
    display_name: str
    definition: str
    formula: str | None = None
    unit: str | None = None
    data_source_refs: list[str] = Field(default_factory=list)
    alias_bindings: list[GlossaryAliasBinding] = Field(default_factory=list)
    concept_relations: list[GlossaryConceptRelation] = Field(default_factory=list)
    scope: GlossaryScope
    version: int
    authoritative: bool


def locale_value(text: LocalizedText, locale: str, fallback: str = "en") -> str:
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"unsupported requested glossary locale: {locale}")
    if locale in text.values:
        return text.values[locale]
    if fallback in text.values:
        return text.values[fallback]
    return next(iter(text.values.values()))
