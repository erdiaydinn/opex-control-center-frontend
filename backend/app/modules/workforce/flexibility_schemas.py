from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator


_CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
_DATE = r"^\d{4}-\d{2}-\d{2}$"
_ACTIVITY_KEY = r"^[a-z][a-z0-9_]{1,63}$"


class AvailabilityUpsertRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    date: str = Field(pattern=_DATE)
    available: bool = True
    earliest_start: str | None = Field(default=None, pattern=_CLOCK)
    latest_end: str | None = Field(default=None, pattern=_CLOCK)
    preferred_start: str | None = Field(default=None, pattern=_CLOCK)
    preferred_end: str | None = Field(default=None, pattern=_CLOCK)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_windows(self):
        if not self.available and any(
            value for value in (
                self.earliest_start,
                self.latest_end,
                self.preferred_start,
                self.preferred_end,
            )
        ):
            raise ValueError("Unavailable days cannot define time windows")
        if bool(self.earliest_start) != bool(self.latest_end):
            raise ValueError("earliest_start and latest_end must be supplied together")
        if bool(self.preferred_start) != bool(self.preferred_end):
            raise ValueError("preferred_start and preferred_end must be supplied together")
        return self


class WorkActivityApproveRequest(BaseModel):
    activity_key: str = Field(pattern=_ACTIVITY_KEY)
    display_name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    unit_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    demand_mode: str = Field(pattern=r"^(VOLUME|FIXED|EVENT)$")
    effective_from: str = Field(pattern=_DATE)
    source_ref: str = Field(min_length=3, max_length=300)
    required_skill_keys: list[str] = Field(default_factory=list, max_length=50)
    required_certification_keys: list[str] = Field(default_factory=list, max_length=50)
    required_equipment_keys: list[str] = Field(default_factory=list, max_length=50)
    safety_tags: list[str] = Field(default_factory=list, max_length=50)
    location_types: list[str] = Field(default_factory=list, max_length=50)

    @field_validator(
        "required_skill_keys",
        "required_certification_keys",
        "required_equipment_keys",
        "safety_tags",
        "location_types",
    )
    @classmethod
    def validate_keys(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Capability keys must be unique")
        if any(len(value) > 80 for value in normalized):
            raise ValueError("Capability keys cannot exceed 80 characters")
        return normalized


class OpenShiftCreateRequest(BaseModel):
    warehouse_id: str = Field(min_length=1, max_length=80)
    date: str = Field(pattern=_DATE)
    start: str = Field(pattern=_CLOCK)
    end: str = Field(pattern=_CLOCK)
    break_minutes: int = Field(default=60, ge=0, le=180)
    role: str = Field(default="Worker", min_length=2, max_length=100)
    activity_keys: list[str] = Field(default_factory=list, max_length=20)
    capacity: int = Field(default=1, ge=1, le=50)
    note: str = Field(default="", max_length=500)

    @field_validator("activity_keys")
    @classmethod
    def validate_activity_keys(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Open-shift activity keys must be unique")
        if any(not re.fullmatch(_ACTIVITY_KEY, value) for value in normalized):
            raise ValueError("Open-shift activity keys must use stable snake_case")
        return normalized


class OpenShiftClaimRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
