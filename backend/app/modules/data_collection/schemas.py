from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_LOCALES = frozenset({"tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"})


def validate_i18n(values: dict[str, str]) -> dict[str, str]:
    unknown = set(values) - SUPPORTED_LOCALES
    if unknown:
        raise ValueError(f"unsupported locales: {', '.join(sorted(unknown))}")
    if any(not value.strip() for value in values.values()):
        raise ValueError("translations must not be blank")
    return values


class FieldType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    BARCODE = "barcode"
    LOT = "lot"
    QUANTITY = "quantity"
    PHOTO = "photo"
    SELECT = "select"


class RecordKind(StrEnum):
    PRODUCT = "product"
    LOT = "lot"
    PALLET = "pallet"
    FIXTURE = "fixture"
    CABINET = "cabinet"
    ASSET = "asset"
    GENERIC = "generic"


class CollectionField(BaseModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=160)
    label_i18n: dict[str, str] = Field(default_factory=dict)
    field_type: FieldType
    required: bool = False
    options: tuple[str, ...] = ()
    unit: str | None = Field(default=None, max_length=32)
    min_value: float | None = None
    max_value: float | None = None

    @model_validator(mode="after")
    def validate_options_and_range(self) -> "CollectionField":
        validate_i18n(self.label_i18n)
        if self.field_type is FieldType.SELECT and not self.options:
            raise ValueError("select fields require options")
        if self.field_type is not FieldType.SELECT and self.options:
            raise ValueError("options are only valid for select fields")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value cannot exceed max_value")
        return self

    def display_label(self, locale: str) -> str:
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported requested locale: {locale}")
        return self.label_i18n.get(locale) or self.label_i18n.get("en") or self.label


class CollectionTemplate(BaseModel):
    template_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=160)
    name_i18n: dict[str, str] = Field(default_factory=dict)
    version: int = Field(ge=1)
    record_kind: RecordKind
    fields: tuple[CollectionField, ...] = Field(min_length=1, max_length=200)

    @field_validator("fields")
    @classmethod
    def unique_field_keys(cls, fields: tuple[CollectionField, ...]) -> tuple[CollectionField, ...]:
        keys = [field.key for field in fields]
        if len(keys) != len(set(keys)):
            raise ValueError("field keys must be unique")
        return fields

    @model_validator(mode="after")
    def validate_name_i18n(self) -> "CollectionTemplate":
        validate_i18n(self.name_i18n)
        return self

    def display_name(self, locale: str) -> str:
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported requested locale: {locale}")
        return self.name_i18n.get(locale) or self.name_i18n.get("en") or self.name


class SubmissionContext(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=80)
    location_id: str = Field(min_length=1, max_length=120)
    actor_id: str = Field(min_length=1, max_length=160)
    source: str = Field(default="web", pattern=r"^(web|mobile|api|bulk|scanner)$")
    captured_at: datetime
    device_id: str | None = Field(default=None, max_length=160)


class CollectionSubmission(BaseModel):
    template_id: str = Field(min_length=3, max_length=80)
    template_version: int = Field(ge=1)
    external_record_id: str | None = Field(default=None, max_length=160)
    context: SubmissionContext
    values: dict[str, Any]


class ValidatedSubmission(BaseModel):
    template_id: str
    template_version: int
    record_kind: RecordKind
    context: SubmissionContext
    normalized_values: dict[str, Any]
    external_record_id: str | None = None
