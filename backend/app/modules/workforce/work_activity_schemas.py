from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


_DATE = r"^\d{4}-\d{2}-\d{2}$"
_KEY = r"^[a-z][a-z0-9_]{1,79}$"


def _keys(values: list[str]) -> list[str]:
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if len(normalized) != len(set(normalized)):
        raise ValueError("Capability keys must be unique")
    if any(not re.fullmatch(_KEY, value) for value in normalized):
        raise ValueError("Capability keys must use stable snake_case")
    return sorted(normalized)


class ActivityLaborStandardApproveRequest(BaseModel):
    activity_key: str = Field(pattern=_KEY)
    seconds_per_unit: float = Field(gt=0, le=86_400)
    people: float = Field(default=1, gt=0, le=100)
    effective_from: str = Field(pattern=_DATE)
    source_ref: str = Field(min_length=3, max_length=300)


class EmployeeCapabilitiesUpdateRequest(BaseModel):
    skill_keys: list[str] = Field(default_factory=list, max_length=100)
    certification_keys: list[str] = Field(default_factory=list, max_length=100)
    equipment_keys: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("skill_keys", "certification_keys", "equipment_keys")
    @classmethod
    def validate_keys(cls, values: list[str]) -> list[str]:
        return _keys(values)


class WorksiteTypeUpdateRequest(BaseModel):
    location_type: str = Field(pattern=_KEY)
