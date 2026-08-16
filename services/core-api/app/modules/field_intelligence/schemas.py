from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.localization import SUPPORTED_LOCALE_SET


class LocalizedText(BaseModel):
    values: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_locales(self) -> "LocalizedText":
        unknown = set(self.values) - SUPPORTED_LOCALE_SET
        if unknown:
            raise ValueError(f"unsupported locales: {', '.join(sorted(unknown))}")
        if any(not value.strip() for value in self.values.values()):
            raise ValueError("localized values must not be blank")
        return self


class LocationUpsert(BaseModel):
    location_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    groups: tuple[str, ...] = Field(default=(), max_length=50)
    active: bool = True
    source_ref: str | None = Field(default=None, max_length=300)


class TemplateCreate(BaseModel):
    template_id: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    version: int = Field(ge=1)
    name: LocalizedText
    schema: dict
    status: Literal["draft", "active"] = "draft"


class TargetSelector(BaseModel):
    all_active_locations: bool = False
    countries: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    districts: tuple[str, ...] = ()
    location_groups: tuple[str, ...] = ()
    include_location_ids: tuple[str, ...] = ()
    exclude_location_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_positive_selector(self) -> "TargetSelector":
        positive = (
            self.all_active_locations
            or self.countries
            or self.regions
            or self.cities
            or self.districts
            or self.location_groups
            or self.include_location_ids
        )
        if not positive:
            raise ValueError("at least one positive target selector is required")
        return self


class MissionCreate(BaseModel):
    template_id: str = Field(min_length=3, max_length=120)
    template_version: int = Field(ge=1)
    title: LocalizedText
    instructions: LocalizedText | None = None
    priority: Literal["normal", "high", "critical"] = "normal"
    target_selector: TargetSelector
    assigned_at: datetime
    deadline_at: datetime
    activate: bool = False

    @model_validator(mode="after")
    def validate_deadline(self) -> "MissionCreate":
        if self.deadline_at <= self.assigned_at:
            raise ValueError("deadline_at must be after assigned_at")
        return self


class FieldScope(BaseModel):
    unrestricted: bool = False
    regions: frozenset[str] = frozenset()
    location_ids: frozenset[str] = frozenset()

    @property
    def empty(self) -> bool:
        return not self.unrestricted and not self.regions and not self.location_ids
