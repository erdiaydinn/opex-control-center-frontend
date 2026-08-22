from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

OperationalSourceDomain = Literal[
    "audit",
    "inventory",
    "dockos",
    "planogram",
    "workforce",
    "field_intelligence",
    "fraud",
    "safety",
]
MetricDirection = Literal["higher_better", "lower_better"]


class OperationalMappingCreateRequest(BaseModel):
    source_subject: str = Field(min_length=1, max_length=255)
    source_domain: OperationalSourceDomain
    signal_type: str = Field(min_length=2, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    skill_id: UUID
    required_level: int = Field(ge=1, le=5)
    recommended_path_id: UUID
    minimum_severity: int = Field(default=1, ge=1, le=5)
    metric_key: str = Field(min_length=2, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    metric_direction: MetricDirection
    mapping_version: int = Field(default=1, ge=1)


class OperationalMappingRetireRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class OperationalSignalIngestRequest(BaseModel):
    source_domain: OperationalSourceDomain
    signal_type: str = Field(min_length=2, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    subject: str = Field(min_length=1, max_length=255)
    severity: int = Field(ge=1, le=5)
    source_ref: str = Field(min_length=1, max_length=255)
    source_version: str = Field(min_length=1, max_length=120)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurred_at: datetime


class OperationalOutcomeObservationRequest(BaseModel):
    source_domain: OperationalSourceDomain
    source_ref: str = Field(min_length=1, max_length=255)
    source_version: str = Field(min_length=1, max_length=120)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_value: float
    observed_value: float
    window_start: datetime
    window_end: datetime
    observed_at: datetime

    @model_validator(mode="after")
    def validate_window(self) -> "OperationalOutcomeObservationRequest":
        if self.window_end < self.window_start:
            raise ValueError("Operational observation window_end cannot precede window_start")
        if self.observed_at < self.window_end:
            raise ValueError("Operational observation observed_at cannot precede window_end")
        return self
