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


class RecruitmentHireActivate(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    employee_id: str = Field(min_length=1, max_length=50)
    roster_ids: list[str] = Field(min_length=1, max_length=20)
    full_name: str = Field(min_length=2, max_length=180)
    tckn: str = Field(pattern=r"^\d{11}$")
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=50)
    employment_start: date
    first_shift: "RecruitmentFirstShift"

    @model_validator(mode="after")
    def bind_first_shift_to_roster(self):
        if self.first_shift.roster_id is None:
            self.first_shift.roster_id = self.roster_ids[0]
        if self.first_shift.roster_id not in self.roster_ids:
            raise ValueError("İlk vardiya roster_id değeri işe giriş roster kimliklerinden biri olmalıdır.")
        return self


class RecruitmentFirstShift(BaseModel):
    roster_id: str | None = Field(default=None, min_length=1, max_length=80)
    date: date
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    break_minutes: int = Field(default=60, ge=0, le=180)


RecruitmentHireActivate.model_rebuild()


class RecruitmentCandidateCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    source_ref: str = Field(min_length=1, max_length=180)
    note: str | None = Field(default=None, max_length=2000)


class RecruitmentCandidateUploadCapabilityCreate(BaseModel):
    document_type: str = Field(
        pattern=r"^(CRIMINAL_RECORD|RESIDENCE|SGK_SERVICE|MILITARY_STATUS|EDUCATION|CIVIL_REGISTRY|OTHER)$"
    )
    expires_in_minutes: int = Field(default=60, ge=5, le=1440)


class RecruitmentCandidateDecision(BaseModel):
    decision: str = Field(pattern=r"^(APPROVED|REJECTED)$")
    note: str = Field(min_length=1, max_length=2000)


class RecruitmentCandidateDocumentVerification(BaseModel):
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: str = Field(pattern=r"^(VERIFIED|FAILED|INCONCLUSIVE)$")
    subject_match: str = Field(pattern=r"^(MATCH|MISMATCH|NOT_CHECKED)$")
    document_type: str = Field(
        pattern=r"^(CRIMINAL_RECORD|RESIDENCE|SGK_SERVICE|MILITARY_STATUS|EDUCATION|CIVIL_REGISTRY|OTHER)$"
    )
    official_receipt_id: str = Field(min_length=1, max_length=240)
    official_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: date | None = None
    note: str = Field(min_length=1, max_length=2000)


class RecruitmentCandidateDocumentAttestation(BaseModel):
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str = Field(min_length=1, max_length=2000)


class RecruitmentHrActualRow(BaseModel):
    employee_id: str | None = Field(default=None, max_length=80)
    tckn: str | None = Field(default=None, pattern=r"^\d{11}$")
    warehouse: str = Field(min_length=1, max_length=180)
    position: str = Field(default="", max_length=180)
    fte: float = Field(default=1.0, ge=0, le=2)
    active: bool = True

    @model_validator(mode="after")
    def require_identity(self):
        if not (str(self.employee_id or "").strip() or str(self.tckn or "").strip()):
            raise ValueError("HR Actual satırında employee_id veya TCKN zorunludur.")
        return self


class RecruitmentHrActualImport(BaseModel):
    source_name: str = Field(min_length=1, max_length=240)
    as_of: date
    rows: list[RecruitmentHrActualRow] = Field(min_length=1, max_length=20000)


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
    base_norm: int | None = Field(default=None, ge=0, le=500)
    temporary_adjustment: int = Field(default=0, ge=-20, le=20)
    temporary_effective_from: date | None = None
    temporary_effective_until: date | None = None
    reversion_mode: str = Field(default="AUTOMATIC_REVIEW", pattern=r"^(AUTOMATIC|AUTOMATIC_REVIEW)$")

    @model_validator(mode="after")
    def validate_temporary_norm(self):
        if self.temporary_adjustment:
            if not self.temporary_effective_from or not self.temporary_effective_until:
                raise ValueError("Geçici norm değişikliğinde başlangıç ve bitiş tarihi zorunludur.")
            if self.temporary_effective_until < self.temporary_effective_from:
                raise ValueError("Geçici norm bitiş tarihi başlangıçtan önce olamaz.")
            if self.base_norm is None:
                self.base_norm = self.norm - self.temporary_adjustment
        return self
