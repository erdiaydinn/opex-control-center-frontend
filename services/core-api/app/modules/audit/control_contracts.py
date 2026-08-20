from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from .schemas import ActionPriority, ActionRisk, StrictModel

EvidenceModality = Literal[
    "VISUAL",
    "VIDEO",
    "DOCUMENT",
    "SENSOR",
    "SYSTEM_DATA",
    "HUMAN_ATTESTATION",
    "OBSERVATION",
]
VisionCapability = Literal[
    "object_detection",
    "zero_shot_detection",
    "segmentation",
    "ocr",
    "visual_reasoning",
    "temporal_video",
]
AuditAnswerValue = Literal["YES", "NO"]
AuditCompoundPolicy = Literal["SINGLE", "ALL", "ANY"]


class AuditVisionContract(StrictModel):
    model_record_id: str = Field(min_length=1, max_length=180)
    required_capabilities: tuple[VisionCapability, ...] = Field(min_length=1, max_length=6)
    minimum_views: int = Field(default=1, ge=1, le=8)
    minimum_resolution_px: int = Field(default=512, ge=128, le=8192)
    human_review_below: float = Field(default=0.95, ge=0, le=1)
    open_ended_discovery_authoritative: bool = False

    @model_validator(mode="after")
    def validate_capabilities(self) -> AuditVisionContract:
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("vision required_capabilities must be unique")
        if self.open_ended_discovery_authoritative:
            raise ValueError("open-ended visual discovery cannot be authoritative")
        return self


class AuditAnswerSemantics(StrictModel):
    """Versioned answer polarity. Text alone never decides PASS/FAIL authority."""

    expected_answer: AuditAnswerValue
    failure_answer: AuditAnswerValue
    failure_condition: str = Field(min_length=1, max_length=1000)
    allow_not_applicable: bool = False
    applicability_rule_key: str | None = Field(default=None, max_length=180)
    compound_policy: AuditCompoundPolicy = "SINGLE"
    semantic_version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_polarity(self) -> AuditAnswerSemantics:
        if self.expected_answer == self.failure_answer:
            raise ValueError("expected_answer and failure_answer must differ")
        if self.allow_not_applicable and not self.applicability_rule_key:
            raise ValueError(
                "allow_not_applicable requires an explicit applicability_rule_key"
            )
        return self


class AuditEvidenceContract(StrictModel):
    """Evidence sufficiency contract separate from question applicability."""

    required_modalities: tuple[EvidenceModality, ...] = ()
    any_of_modalities: tuple[EvidenceModality, ...] = ()
    minimum_evidence_refs: int = Field(default=0, ge=0, le=50)
    require_privacy_verified_media: bool = True

    @model_validator(mode="after")
    def validate_requirements(self) -> AuditEvidenceContract:
        for values, name in (
            (self.required_modalities, "required_modalities"),
            (self.any_of_modalities, "any_of_modalities"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        return self


class AuditQuestionControl(StrictModel):
    item_key: str = Field(min_length=1, max_length=180)
    evidence_modalities: tuple[EvidenceModality, ...] = Field(min_length=1, max_length=7)
    vision_contract: AuditVisionContract | None = None
    answer_semantics: AuditAnswerSemantics | None = None
    evidence_contract: AuditEvidenceContract | None = None
    risk_class: ActionRisk = "other"
    default_priority: ActionPriority = "medium"
    action_template_key: str | None = Field(default=None, max_length=180)
    owner_rule_key: str | None = Field(default=None, max_length=180)
    sla_rule_key: str | None = Field(default=None, max_length=180)
    closure_evidence_required: bool = True

    @model_validator(mode="after")
    def validate_modalities(self) -> AuditQuestionControl:
        if len(set(self.evidence_modalities)) != len(self.evidence_modalities):
            raise ValueError("question evidence modalities must be unique")
        visual_allowed = (
            "VISUAL" in self.evidence_modalities
            or "VIDEO" in self.evidence_modalities
        )
        if self.vision_contract is not None and not visual_allowed:
            raise ValueError("vision_contract requires VISUAL or VIDEO evidence modality")
        if self.evidence_contract is not None:
            declared = set(self.evidence_modalities)
            required = set(self.evidence_contract.required_modalities)
            alternatives = set(self.evidence_contract.any_of_modalities)
            if not required.issubset(declared) or not alternatives.issubset(declared):
                raise ValueError(
                    "evidence_contract modalities must be declared in evidence_modalities"
                )
        return self


def parse_question_controls(settings: dict[str, object]) -> tuple[AuditQuestionControl, ...]:
    raw = settings.get("question_controls")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("settings.question_controls must be a list")
    controls = tuple(AuditQuestionControl.model_validate(item) for item in raw)
    keys = tuple(control.item_key for control in controls)
    if len(set(keys)) != len(keys):
        raise ValueError("settings.question_controls item_key values must be unique")
    return controls


def question_control_fingerprint(control: AuditQuestionControl) -> str:
    canonical = json.dumps(
        control.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
