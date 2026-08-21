from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


AuditDecision = Literal[
    "PASS",
    "FAIL",
    "NOT_APPLICABLE",
    "REVIEW_REQUIRED",
    "INSUFFICIENT_EVIDENCE",
]
DecisionSource = Literal["AI", "AUDITOR", "MANAGER", "OPERATIONS_STANDARDS"]
ActionRisk = Literal[
    "life_safety",
    "food_safety",
    "legal",
    "operational",
    "brand",
    "quality",
    "other",
]
ActionPriority = Literal["critical", "high", "medium", "low"]
ActionStatus = Literal[
    "open",
    "in_progress",
    "submitted_for_verification",
    "ai_verified",
    "human_verified",
    "rejected",
    "closed",
]
AssuranceManagerDisposition = Literal["AI_CONFIRMED", "AUDITOR_CONFIRMED"]
AssuranceStandardsDisposition = Literal[
    "AI_CONFIRMED",
    "AUDITOR_CONFIRMED",
    "STANDARD_CHANGED",
    "MODEL_REVIEW_REQUIRED",
    "NO_CHANGE",
]


class AuditProgramCreate(StrictModel):
    program_key: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    version: int = Field(gt=0)
    name_i18n: dict[str, str] = Field(min_length=1)
    field_template_id: str = Field(min_length=1, max_length=120)
    field_template_version: int = Field(gt=0)
    scoring_policy: dict[str, object] = Field(default_factory=dict)
    settings: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_program_contract(self) -> AuditProgramCreate:
        blank = any(
            not key.strip() or not value.strip()
            for key, value in self.name_i18n.items()
        )
        if blank:
            raise ValueError("program localized names must not be blank")
        # Lazy import avoids making the generic schema module depend on Audit control types at
        # import time while still rejecting malformed versioned standards before persistence.
        from .control_contracts import parse_question_controls

        parse_question_controls(self.settings)
        return self


class AuditProgramActivate(StrictModel):
    effective_from: datetime


class AuditLocationManagerAssignmentCreate(StrictModel):
    manager_membership_id: UUID
    source_ref: str = Field(min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, gt=0)


class AuditRunStart(StrictModel):
    program_key: str = Field(min_length=1, max_length=120)
    program_version: int = Field(gt=0)
    location_id: str = Field(min_length=1, max_length=120)
    field_mission_id: UUID | None = None
    # Compatibility only: caller identity is never accepted as manager authority.
    manager_subject: None = None
    source_mode: Literal[
        "checklist",
        "photo",
        "video",
        "guided_video",
        "mixed",
    ] = "checklist"


class AuditDecisionEventCreate(StrictModel):
    item_key: str = Field(min_length=1, max_length=180)
    decision_source: DecisionSource
    decision: AuditDecision
    confidence: float | None = Field(default=None, ge=0, le=1)
    model_or_rule_ref: str | None = Field(default=None, max_length=300)
    reason: str | None = Field(default=None, max_length=4000)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def validate_ai_provenance(self) -> AuditDecisionEventCreate:
        if self.decision_source == "AI" and not self.model_or_rule_ref:
            raise ValueError("AI decisions require model_or_rule_ref")
        invalid_ref = any(
            not ref.strip() or len(ref) > 500
            for ref in self.evidence_refs
        )
        if invalid_ref:
            raise ValueError("evidence refs must be non-blank and <= 500 characters")
        return self


class AuditRedactionReceiptCreate(StrictModel):
    location_id: str = Field(min_length=1, max_length=120)
    device_id: str | None = Field(default=None, max_length=180)
    media_kind: Literal["image", "video"]
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    redacted_evidence_ref: str = Field(min_length=1, max_length=500)
    privacy_policy_version: str = Field(min_length=1, max_length=80)
    detector_model_ref: str = Field(min_length=1, max_length=300)
    frame_count: int = Field(gt=0)
    processed_frame_count: int = Field(gt=0)

    @model_validator(mode="after")
    def require_complete_redaction(self) -> AuditRedactionReceiptCreate:
        if self.processed_frame_count != self.frame_count:
            raise ValueError("redaction coverage must include every canonical frame")
        return self


class AuditActionCreate(StrictModel):
    item_key: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=8000)
    risk_class: ActionRisk
    priority: ActionPriority
    assignee_subject: str | None = Field(default=None, max_length=255)
    due_at: datetime


class AuditActionUpdate(StrictModel):
    expected_version: int = Field(gt=0)
    status: ActionStatus
    assignee_subject: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None
    closure_evidence_ref: str | None = Field(default=None, max_length=500)
    verification_receipt_ref: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def verified_status_requires_receipts(self) -> AuditActionUpdate:
        verified = self.status in {"ai_verified", "human_verified", "closed"}
        missing_receipt = (
            not self.closure_evidence_ref
            or not self.verification_receipt_ref
        )
        if verified and missing_receipt:
            raise ValueError(
                "verified/closed actions require closure evidence "
                "and verification receipt"
            )
        return self


class AuditAssuranceReviewCreate(StrictModel):
    item_key: str = Field(min_length=1, max_length=180)
    state: Literal[
        "MANAGER_REVIEW",
        "OPERATIONS_STANDARDS_REVIEW",
        "RESOLVED",
    ]
    disposition: AssuranceStandardsDisposition
    reason: str = Field(min_length=1, max_length=4000)


class AuditManagerAssuranceDecision(StrictModel):
    expected_version: int = Field(gt=0)
    disposition: AssuranceManagerDisposition
    reason: str = Field(min_length=1, max_length=4000)


class AuditStandardsAssuranceDecision(StrictModel):
    expected_version: int = Field(gt=0)
    disposition: AssuranceStandardsDisposition
    reason: str = Field(min_length=1, max_length=4000)
