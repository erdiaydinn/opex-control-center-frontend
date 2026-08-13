from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator


class PlannedDeparture(BaseModel):
    employee_id: str = Field(min_length=1, max_length=50)
    employee_name: str = Field(min_length=2, max_length=180)
    last_working_date: date
    departure_type: str = Field(default="RESIGNATION", pattern=r"^(RESIGNATION|TERMINATION|TRANSFER)$")


class RecruitmentRequestCreate(BaseModel):
    warehouse_id: str = Field(min_length=1, max_length=180)
    position_code: str = Field(pattern=r"^(STORE_STAFF|ASSISTANT_MANAGER|STORE_SUPPORT|STORE_MANAGER)$")
    quantity: int = Field(default=1, ge=1, le=20)
    employment_type: str = Field(default="FULL_TIME", pattern=r"^(FULL_TIME|PART_TIME|TEMPORARY)$")
    reason_code: str = Field(pattern=r"^(NORM_GAP|PLANNED_DEPARTURE|NEW_WAREHOUSE|OTHER)$")
    needed_by: date
    justification: str = Field(min_length=1, max_length=2000)
    planned_departure: PlannedDeparture | None = None

    @model_validator(mode="after")
    def validate_departure(self):
        if self.reason_code == "PLANNED_DEPARTURE" and self.planned_departure is None:
            raise ValueError("Planlı ayrılış talebinde ayrılacak personel bilgisi zorunludur.")
        return self


class RecruitmentDecision(BaseModel):
    decision: str = Field(pattern=r"^(APPROVED|REJECTED)$")
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_rejection_note(self):
        if not self.note.strip():
            raise ValueError("Karar gerekçesi boş bırakılamaz.")
        return self


class RecruitmentSettingsUpdate(BaseModel):
    hr_recipients: list[str] = Field(default_factory=list, max_length=50)
    partner_recipients: list[str] = Field(default_factory=list, max_length=50)
    default_manager_capacity: int = Field(default=1, ge=0, le=10)
    warehouse_manager_capacity: dict[str, int] = Field(default_factory=dict)
    counted_position_codes: list[str] = Field(
        default_factory=lambda: ["STORE_STAFF", "ASSISTANT_MANAGER", "STORE_SUPPORT"]
    )

    @field_validator("hr_recipients", "partner_recipients")
    @classmethod
    def validate_recipients(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            email = value.strip().lower()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                raise ValueError(f"Geçersiz e-posta adresi: {value}")
            if email not in cleaned:
                cleaned.append(email)
        return cleaned


class StaffingNormPatch(BaseModel):
    warehouse: str = Field(min_length=2, max_length=180)
    norm: int = Field(ge=0, le=500)
    regional_manager: str = Field(default="", max_length=180)
    regional_executive: str = Field(default="", max_length=180)
    active: bool = True
