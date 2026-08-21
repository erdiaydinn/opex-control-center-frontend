from datetime import datetime
import re
import unicodedata

from pydantic import BaseModel, Field, field_validator, model_validator


def _header_key(value: object) -> str:
    text = str(value or "").strip().lower().replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z0-9]", "", "".join(char for char in text if not unicodedata.combining(char)))


_IDENTITY_ALIASES = {
    "employee_id": ("employee id", "employee number", "employee no", "personel id", "sicil no", "sicil numarasi", "sap id"),
    "tckn": ("tc", "t.c.", "tck", "tckn", "tc kimlik", "tc kimlik no", "tc kimlik numarasi", "kimlik no", "kimlik numarasi", "national id", "national identity number"),
    "roster_ids": ("roster id", "rooster id", "roster employee id", "picker id", "picker_id", "rider id", "rider_id"),
}


def _normalize_columns(value: object, aliases: dict[str, tuple[str, ...]]) -> object:
    if not isinstance(value, dict):
        return value
    normalized = {_header_key(key): cell for key, cell in value.items()}
    result = dict(value)
    for target, names in aliases.items():
        if result.get(target) not in (None, "", []):
            continue
        for name in (target, *names):
            key = _header_key(name)
            if key in normalized and normalized[key] not in (None, ""):
                result[target] = normalized[key]
                break
    return result


def _normalize_identity_row(value: object, aliases: dict[str, tuple[str, ...]]) -> object:
    result = _normalize_columns(value, {**_IDENTITY_ALIASES, **aliases})
    if not isinstance(result, dict):
        return result
    if isinstance(result.get("roster_ids"), str):
        result["roster_ids"] = [item.strip() for item in re.split(r"[,;|\n]+", result["roster_ids"]) if item.strip()]
    tckn = "".join(character for character in str(result.get("tckn") or "") if character.isdigit())
    if tckn:
        result["tckn"] = tckn
    source = result.get("source_person_id") or result.get("person_id")
    if not source and len(tckn) == 11:
        result["source_person_id"] = tckn
        result["person_id"] = tckn
        result["identity_method"] = "TC"
    return result


class ManualCorrectionRequest(BaseModel):
    check_in: str | None = None
    check_out: str | None = None
    break_minutes: int = Field(default=0, ge=0, le=180)
    reason: str = Field(default="", max_length=500)

    @field_validator("check_in", "check_out")
    @classmethod
    def validate_clock(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("Saat HH:MM biçiminde olmalıdır")
        hour, minute = map(int, parts)
        if hour > 23 or minute > 59:
            raise ValueError("Geçersiz saat")
        return value


class ApprovalRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class BulkApprovalRequest(BaseModel):
    attendance_ids: list[str] = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=500)


class ShiftCreateRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    person_name: str = Field(min_length=2, max_length=150)
    warehouse_id: str = Field(min_length=1, max_length=50)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start: str
    end: str
    break_minutes: int = Field(default=60, ge=0, le=180)
    role: str = Field(default="Picker", min_length=2, max_length=100)

    @field_validator("start", "end")
    @classmethod
    def validate_shift_clock(cls, value: str) -> str:
        return ManualCorrectionRequest.validate_clock(value)  # type: ignore[return-value]


class CheckInRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float = Field(ge=0, le=5000)
    device_id: str = Field(min_length=3, max_length=150)
    device_trusted: bool
    device_key_id: str | None = Field(default=None, max_length=150)
    challenge_id: str | None = Field(default=None, max_length=200)
    signature: str | None = Field(default=None, max_length=2000)
    local_auth_method: str = Field(default="NONE", pattern=r"^(NONE|DEVICE_BIOMETRIC|DEVICE_PASSCODE)$")
    local_auth_at: datetime | None = None
    pilot_simulation: bool = False


class CheckOutRequest(CheckInRequest):
    pass


class BreakActionRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    action: str = Field(pattern=r"^(START|FINISH)$")


class RuleVersionCreateRequest(BaseModel):
    engine_key: str = Field(pattern=r"^(dailyMax|weeklyNormal|annualOvertime|betweenShifts|breakShort|breakMedium|breakLong|earlyCheckIn)$")
    title: str = Field(min_length=3, max_length=150)
    value: int = Field(ge=0, le=100_000)
    level: str = Field(min_length=2, max_length=50)
    effective_from: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field(default="", max_length=500)


class DeviceResetRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class DeviceChallengeRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    device_id: str = Field(min_length=3, max_length=150)


class DeviceRegisterRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    device_id: str = Field(min_length=3, max_length=150)
    enrollment_token: str = Field(min_length=12, max_length=300)
    device_key_id: str = Field(min_length=8, max_length=150)
    public_key: str = Field(min_length=32, max_length=4000)
    attestation_provider: str = Field(pattern=r"^(APPLE_APP_ATTEST|GOOGLE_PLAY_INTEGRITY)$")
    attestation_token: str = Field(min_length=20, max_length=8000)
    model: str = Field(default="", max_length=150)
    os_version: str = Field(default="", max_length=100)
    app_version: str = Field(default="", max_length=50)
    platform: str = Field(default="IOS", pattern=r"^(IOS|ANDROID)$")
    push_token: str = Field(default="", max_length=1000)
    live_activity_token: str | None = Field(default=None, max_length=1000)


class PickerCorrectionCreateRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    shift_id: str = Field(min_length=1, max_length=100)
    request_type: str = Field(min_length=3, max_length=100)
    requested_check_in: str | None = None
    requested_check_out: str | None = None
    reason: str = Field(default="", max_length=1000)

    @field_validator("requested_check_in", "requested_check_out")
    @classmethod
    def validate_requested_clock(cls, value: str | None) -> str | None:
        return ManualCorrectionRequest.validate_clock(value)


class ManagerTaskResolveRequest(BaseModel):
    decision: str = Field(pattern=r"^(APPROVED|REJECTED|CORRECTED)$")
    manager_note: str = Field(default="", max_length=1000)
    requested_check_in: str | None = None
    requested_check_out: str | None = None
    target_minutes: int | None = Field(default=None, ge=0, le=1440)


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(default="", max_length=180)
    message: str = Field(default="", max_length=2000)
    target_type: str = Field(pattern=r"^(all|warehouse|person)$")
    target_value: str = Field(default="", max_length=180)
    publish_at: datetime | None = None


class AnnouncementReceiptRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)


class NotificationPolicyUpdateRequest(BaseModel):
    shift_published: bool = True
    check_in_reminder: bool = True
    check_in_reminder_minutes: int = Field(default=15, ge=0, le=1440)
    check_out_reminder: bool = True
    check_out_reminder_minutes: int = Field(default=15, ge=0, le=1440)


class LeaveRequestCreateRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    person_name: str = Field(min_length=2, max_length=150)
    warehouse: str = Field(min_length=2, max_length=180)
    leave_type: str = Field(pattern=r"^(weekly_off|annual)$")
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field(default="", max_length=1000)


class LeaveRequestResolveRequest(BaseModel):
    decision: str = Field(pattern=r"^(APPROVED|REJECTED)$")
    manager_note: str = Field(default="", max_length=1000)


class FeatureFlagsUpdateRequest(BaseModel):
    breaks: bool = True
    leave_requests: bool = True
    appeals: bool = True
    announcements: bool = True
    notifications: bool = True
    archive: bool = True
    manager_tasks: bool = True
    qr_check_in: bool = False
    live_break_activity: bool = True
    employee_experience: bool = True


class PersonUpsertRequest(BaseModel):
    employee_id: str = Field(min_length=1, max_length=50)
    roster_ids: list[str] = Field(default_factory=list, max_length=20)
    full_name: str = Field(min_length=2, max_length=180)
    tckn: str = Field(pattern=r"^\d{11}$")
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=50)
    position: str = Field(default="Picker", max_length=120)
    warehouse_id: str | None = Field(default=None, max_length=120)
    employment_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    employment_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    active: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_customer_columns(cls, value: object) -> object:
        return _normalize_identity_row(value, {
            "full_name": ("name", "employee name", "ad soyad", "personel adi"),
            "warehouse_id": ("warehouse id", "warehouse code", "depo kodu", "magaza kodu", "store id"),
            "employment_start": ("hire date", "employment start date", "ise giris tarihi", "giris tarihi"),
            "employment_end": ("termination date", "employment end date", "exit date", "isten cikis tarihi", "cikis tarihi", "ayrilis tarihi"),
            "position": ("title", "unvan", "role", "job title"),
            "email": ("e posta", "eposta"),
            "phone": ("telefon", "telefon numarasi"),
        })

    @model_validator(mode="after")
    def validate_employee_master_dates(self):
        if self.employment_start and self.employment_end and self.employment_end < self.employment_start:
            raise ValueError("İşten çıkış tarihi işe giriş tarihinden önce olamaz.")
        return self


class PeopleBulkUpsertRequest(BaseModel):
    rows: list[PersonUpsertRequest] = Field(min_length=1, max_length=5000)


class EmploymentLifecycleRow(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    employment_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    employment_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    identity_method: str = Field(default="TC", max_length=80)

    @model_validator(mode="before")
    @classmethod
    def normalize_customer_columns(cls, value: object) -> object:
        result = _normalize_identity_row(value, {
            "person_id": ("employee id", "employee number", "personel id", "sicil no", "sap id"),
            "source_person_id": ("tc", "tckn", "tc kimlik no", "kimlik numarasi", "national id"),
            "employment_start": ("hire date", "employment start date", "ise giris tarihi", "giris tarihi"),
            "employment_end": ("termination date", "employment end date", "exit date", "isten cikis tarihi", "cikis tarihi", "ayrilis tarihi"),
        })
        if isinstance(result, dict) and result.get("source_person_id") and not result.get("person_id"):
            result["person_id"] = result["source_person_id"]
            result["identity_method"] = "TC"
        return result


class EmploymentLifecycleImportRequest(BaseModel):
    rows: list[EmploymentLifecycleRow] = Field(min_length=1, max_length=10000)
    file_name: str = Field(default="", max_length=255)


class AttendanceImportRow(BaseModel):
    id: str = Field(default="", max_length=180)
    shift_id: str = Field(default="", max_length=180)
    person_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=180)
    role: str = Field(default="Picker", max_length=120)
    warehouse: str = Field(default="", max_length=180)
    date: str = Field(pattern=r"^(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})$")
    planned: str = Field(default="Dosyadan", max_length=80)
    check_in: str | None = Field(default=None, max_length=40)
    check_out: str | None = Field(default=None, max_length=40)
    break_minutes: int = Field(default=0, ge=0, le=1440)
    net_minutes: int = Field(default=0, ge=0, le=1440)
    expected_minutes: int = Field(default=0, ge=0, le=1440)
    status: str = Field(default="Tamamlandı", max_length=120)
    approval: str = Field(default="Onay bekliyor", max_length=120)
    source: str = Field(default="Puantaj Dosyası", max_length=320)
    source_person_id: str = Field(default="", max_length=80)
    identity_method: str = Field(default="", max_length=80)

    @model_validator(mode="before")
    @classmethod
    def normalize_customer_columns(cls, value: object) -> object:
        return _normalize_identity_row(value, {
            "person_id": ("employee id", "employee number", "personel id", "sicil no", "roster id", "picker id", "rider id"),
            "source_person_id": ("employee id", "employee number", "personel id", "sicil no", "roster id", "picker id", "rider id"),
            "name": ("employee name", "personel adi", "ad soyad", "picker name", "rider name"),
            "date": ("shift date", "vardiya tarihi", "tarih"),
            "check_in": ("check in", "giris", "giris saati", "baslangic"),
            "check_out": ("check out", "cikis", "cikis saati", "bitis"),
            "break_minutes": ("break minutes", "mola dakika", "mola suresi"),
            "net_minutes": ("net minutes", "net dakika", "net sure", "gunluk net"),
            "warehouse": ("warehouse name", "depo", "depo adi", "store"),
        })


class AttendanceImportRequest(BaseModel):
    rows: list[AttendanceImportRow] = Field(min_length=1, max_length=50000)
    file_name: str = Field(default="", max_length=255)


class LeaveImportRow(BaseModel):
    id: str = Field(default="", max_length=180)
    person_id: str = Field(min_length=1, max_length=50)
    person_name: str = Field(default="", max_length=180)
    warehouse: str = Field(default="", max_length=180)
    type_id: str = Field(min_length=1, max_length=120)
    category: str = Field(default="", max_length=180)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    minutes: int = Field(default=0, ge=0, le=1440)
    approval: str = Field(default="Onaylandı", max_length=80)
    note: str = Field(default="", max_length=1000)
    source: str = Field(default="Time Off Used", max_length=255)
    source_person_id: str = Field(default="", max_length=80)
    identity_method: str = Field(default="", max_length=80)

    @model_validator(mode="before")
    @classmethod
    def normalize_customer_columns(cls, value: object) -> object:
        return _normalize_identity_row(value, {
            "person_id": ("employee id", "employee number", "personel id", "sicil no", "roster id", "picker id", "rider id"),
            "source_person_id": ("employee id", "employee number", "personel id", "sicil no", "roster id", "picker id", "rider id"),
            "person_name": ("employee name", "personel adi", "ad soyad", "name"),
            "type_id": ("leave type id", "izin tipi kodu", "izin turu kodu"),
            "category": ("leave category", "izin tipi", "izin turu", "time off type"),
            "date": ("leave date", "izin tarihi", "tarih", "date"),
            "minutes": ("leave minutes", "izin dakika", "sure dakika"),
            "warehouse": ("warehouse name", "depo", "depo adi", "store"),
        })


class LeaveImportRequest(BaseModel):
    rows: list[LeaveImportRow] = Field(min_length=1, max_length=50000)
    file_name: str = Field(default="", max_length=255)


class WarehouseUpsertRequest(BaseModel):
    id: str | None = Field(default=None, max_length=160)
    name: str = Field(min_length=2, max_length=180)
    latitude: float = Field(ge=35, le=43)
    longitude: float = Field(ge=25, le=46)
    m2: int = Field(default=0, ge=0, le=100_000)
    radius: int = Field(default=120, ge=20, le=2000)
    max_accuracy: int = Field(default=50, ge=5, le=500)
    active: bool = True


class WarehouseBulkPatchRequest(BaseModel):
    warehouse_ids: list[str] = Field(min_length=1, max_length=500)
    radius: int | None = Field(default=None, ge=20, le=2000)
    max_accuracy: int | None = Field(default=None, ge=5, le=500)
    active: bool | None = None
