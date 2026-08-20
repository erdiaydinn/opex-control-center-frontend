from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


_CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
_DATE = r"^\d{4}-\d{2}-\d{2}$"


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


class OpenShiftCreateRequest(BaseModel):
    warehouse_id: str = Field(min_length=1, max_length=80)
    date: str = Field(pattern=_DATE)
    start: str = Field(pattern=_CLOCK)
    end: str = Field(pattern=_CLOCK)
    break_minutes: int = Field(default=60, ge=0, le=180)
    role: str = Field(default="Picker", min_length=2, max_length=100)
    capacity: int = Field(default=1, ge=1, le=50)
    note: str = Field(default="", max_length=500)


class OpenShiftClaimRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
