from __future__ import annotations

from datetime import datetime
import re

from pydantic import BaseModel, Field, field_validator, model_validator


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


class WorkloadSignalPreviewRequest(BaseModel):
    driver_key: str = Field(min_length=2, max_length=160)
    activity_key: str = Field(pattern=_KEY)
    demand_mode: str = Field(pattern=r"^(VOLUME|FIXED|EVENT)$")
    quantity: float = Field(ge=0, le=100_000_000)
    source_ref: str = Field(min_length=3, max_length=300)


class WorkActivityDemandPreviewRequest(BaseModel):
    worksite_id: str = Field(min_length=1, max_length=120)
    interval_start: datetime
    interval_minutes: int = Field(default=60)
    model_version: str = Field(default="generic-work-activity-v1", min_length=3, max_length=120)
    signals: list[WorkloadSignalPreviewRequest] = Field(min_length=1, max_length=200)

    @field_validator("interval_minutes")
    @classmethod
    def validate_interval(cls, value: int) -> int:
        if value not in {15, 30, 60}:
            raise ValueError("interval_minutes must be one of 15, 30 or 60")
        return value

    @model_validator(mode="after")
    def validate_preview(self):
        if self.interval_start.tzinfo is None or self.interval_start.utcoffset() is None:
            raise ValueError("interval_start must include timezone offset")
        driver_keys = [signal.driver_key for signal in self.signals]
        if len(driver_keys) != len(set(driver_keys)):
            raise ValueError("driver_key values must be unique")
        return self
