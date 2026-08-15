from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_LOCALES = frozenset({"tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"})


class MissionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TargetStatus(StrEnum):
    UNSEEN = "unseen"
    SEEN = "seen"
    STARTED = "started"
    PARTIAL = "partial"
    SUBMITTED = "submitted"
    REWORK = "rework"
    VERIFIED = "verified"
    OVERDUE = "overdue"
    EXEMPT = "exempt"


class MissionPriority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class ReminderTrigger(StrEnum):
    AFTER_ASSIGNMENT = "after_assignment"
    BEFORE_DEADLINE = "before_deadline"
    AFTER_DEADLINE = "after_deadline"
    REWORK_REQUIRED = "rework_required"


class ReminderChannel(StrEnum):
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"


class LocalizedMessage(BaseModel):
    values: dict[str, str] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def validate_locales(cls, values: dict[str, str]) -> dict[str, str]:
        unknown = set(values) - SUPPORTED_LOCALES
        if unknown:
            raise ValueError(f"unsupported locales: {', '.join(sorted(unknown))}")
        if any(not value.strip() for value in values.values()):
            raise ValueError("localized mission text must not be blank")
        return values


class LocationRecord(BaseModel):
    tenant_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    country: str = Field(min_length=1)
    region: str | None = None
    city: str | None = None
    district: str | None = None
    groups: tuple[str, ...] = ()
    active: bool = True


class TargetSelector(BaseModel):
    tenant_id: str = Field(min_length=1)
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
        positives = (
            self.all_active_locations,
            self.countries,
            self.regions,
            self.cities,
            self.districts,
            self.location_groups,
            self.include_location_ids,
        )
        if not any(positives):
            raise ValueError("mission target selector requires at least one positive scope")
        return self


class TargetSnapshot(BaseModel):
    tenant_id: str
    created_at: datetime
    location_ids: tuple[str, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReminderStep(BaseModel):
    step_id: str = Field(min_length=1, max_length=80)
    trigger: ReminderTrigger
    offset_minutes: int = Field(ge=0, le=10080)
    channels: tuple[ReminderChannel, ...] = Field(min_length=1)
    eligible_statuses: tuple[TargetStatus, ...] = Field(min_length=1)
    escalate_to_role: str | None = Field(default=None, max_length=100)
    message: LocalizedMessage


class ReminderPolicy(BaseModel):
    steps: tuple[ReminderStep, ...] = Field(default_factory=tuple, max_length=20)
    digest_non_critical: bool = True
    max_notifications_per_target_per_day: int = Field(default=6, ge=1, le=24)

    @field_validator("steps")
    @classmethod
    def unique_step_ids(cls, steps: tuple[ReminderStep, ...]) -> tuple[ReminderStep, ...]:
        ids = [step.step_id for step in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("reminder step ids must be unique")
        return steps


class MissionDefinition(BaseModel):
    mission_id: str = Field(min_length=3, max_length=100)
    tenant_id: str = Field(min_length=1)
    template_id: str = Field(min_length=3, max_length=80)
    template_version: int = Field(ge=1)
    title: LocalizedMessage
    instructions: LocalizedMessage
    priority: MissionPriority = MissionPriority.NORMAL
    status: MissionStatus = MissionStatus.DRAFT
    target_selector: TargetSelector
    assigned_at: datetime
    deadline_at: datetime
    reminder_policy: ReminderPolicy = Field(default_factory=ReminderPolicy)
    requires_managed_device: bool = False
    requires_location_proof: bool = False

    @model_validator(mode="after")
    def validate_mission(self) -> "MissionDefinition":
        if self.target_selector.tenant_id != self.tenant_id:
            raise ValueError("target selector tenant must match mission tenant")
        if self.deadline_at <= self.assigned_at:
            raise ValueError("deadline must be after assignment")
        return self


class TargetProgress(BaseModel):
    tenant_id: str
    mission_id: str
    location_id: str
    status: TargetStatus
    updated_at: datetime
    notification_count_today: int = Field(default=0, ge=0)


class ReminderAction(BaseModel):
    mission_id: str
    location_id: str
    step_id: str
    channels: tuple[ReminderChannel, ...]
    escalate_to_role: str | None = None
    message: LocalizedMessage
