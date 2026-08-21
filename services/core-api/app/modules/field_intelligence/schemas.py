from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.localization import SUPPORTED_LOCALE_SET

FIELD_INPUT_TYPES = frozenset(
    {
        "text",
        "number",
        "select",
        "barcode",
        "qr",
        "photo",
        "lot",
        "batch",
        "expiry",
        "quantity",
        "measurement",
        "gps",
        "yes_no",
        "multi_row",
    }
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalizedText(StrictModel):
    values: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_locales(self) -> LocalizedText:
        unknown = set(self.values) - SUPPORTED_LOCALE_SET
        if unknown:
            raise ValueError(f"unsupported locales: {', '.join(sorted(unknown))}")
        if any(not value.strip() for value in self.values.values()):
            raise ValueError("localized values must not be blank")
        return self


class LocationUpsert(StrictModel):
    location_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    groups: tuple[str, ...] = Field(default=(), max_length=50)
    active: bool = True
    source_ref: str | None = Field(default=None, max_length=300)


class TemplateFieldDefinition(StrictModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
    type: str = Field(min_length=1, max_length=40)
    label: LocalizedText
    required: bool = False
    helper: LocalizedText | None = None
    options: tuple[str, ...] = Field(default=(), max_length=100)
    unit: str | None = Field(default=None, max_length=40)
    config: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_type_and_options(self) -> TemplateFieldDefinition:
        if self.type not in FIELD_INPUT_TYPES:
            raise ValueError(f"unsupported field type: {self.type}")
        if self.type == "select" and not self.options:
            raise ValueError("select fields require options")
        if self.type != "select" and self.options:
            raise ValueError("options are only valid for select fields")
        return self


class TemplateSchema(StrictModel):
    fields: tuple[TemplateFieldDefinition, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_field_keys(self) -> TemplateSchema:
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("template field keys must be unique")
        return self


class EvidencePolicy(StrictModel):
    camera_only_photo: bool = False
    managed_device_required: bool = False


class EvidenceObjectClaim(StrictModel):
    receipt_id: UUID
    field_key: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$",
    )
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["image/jpeg", "image/png", "image/heic", "image/webp"]
    byte_size: int = Field(gt=0, le=26_214_400)
    capture_session_id: UUID | None = None


class TemplateCreate(StrictModel):
    template_id: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    version: int = Field(ge=1)
    name: LocalizedText
    schema: TemplateSchema
    status: Literal["draft", "active"] = "draft"


class TargetSelector(StrictModel):
    all_active_locations: bool = False
    countries: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    districts: tuple[str, ...] = ()
    location_groups: tuple[str, ...] = ()
    include_location_ids: tuple[str, ...] = ()
    exclude_location_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_positive_selector(self) -> TargetSelector:
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
        overlap = set(self.include_location_ids) & set(self.exclude_location_ids)
        if overlap:
            raise ValueError("a location cannot be both included and excluded")
        return self


class MissionCreate(StrictModel):
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
    def validate_deadline(self) -> MissionCreate:
        if self.deadline_at <= self.assigned_at:
            raise ValueError("deadline_at must be after assigned_at")
        return self


class EvidenceSubmit(StrictModel):
    client_submission_id: UUID
    payload: dict[str, object] = Field(min_length=1, max_length=100)
    device_id: str | None = Field(default=None, max_length=180)
    observed_at: datetime | None = None


class OfflineEvidenceEvent(StrictModel):
    client_submission_id: UUID
    mission_id: UUID
    location_id: str = Field(min_length=1, max_length=120)
    device_id: str = Field(min_length=8, max_length=180)
    device_sequence: int = Field(gt=0)
    target_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    captured_at: datetime
    payload: dict[str, object] = Field(min_length=1, max_length=100)
    evidence_objects: tuple[EvidenceObjectClaim, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_capture_identity(self) -> OfflineEvidenceEvent:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        receipt_ids = [claim.receipt_id for claim in self.evidence_objects]
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError("offline event contains duplicate evidence receipt ids")
        field_keys = [claim.field_key for claim in self.evidence_objects]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("offline event contains duplicate evidence object field keys")
        return self


class OfflineSyncBatch(StrictModel):
    events: tuple[OfflineEvidenceEvent, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_batch_identities(self) -> OfflineSyncBatch:
        sequences = [(event.device_id, event.device_sequence) for event in self.events]
        if len(sequences) != len(set(sequences)):
            raise ValueError("batch contains duplicate device sequence identities")
        submissions = [event.client_submission_id for event in self.events]
        if len(submissions) != len(set(submissions)):
            raise ValueError("batch contains duplicate client submission ids")
        return self


class EvidenceReview(StrictModel):
    decision: Literal["accept", "rework", "reject"]
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_reason(self) -> EvidenceReview:
        if self.decision != "accept" and not (self.reason or "").strip():
            raise ValueError("rework or reject decision requires a reason")
        return self


class NotificationIntentCreate(StrictModel):
    kind: Literal["reminder", "escalation"]
    reason_code: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    location_ids: tuple[str, ...] = Field(default=(), max_length=500)


class FieldScope(StrictModel):
    unrestricted: bool = False
    regions: frozenset[str] = frozenset()
    location_ids: frozenset[str] = frozenset()

    @property
    def empty(self) -> bool:
        return not self.unrestricted and not self.regions and not self.location_ids
