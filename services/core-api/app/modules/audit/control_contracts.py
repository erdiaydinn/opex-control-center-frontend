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
]
VisionCapability = Literal[
    "object_detection",
    "zero_shot_detection",
    "segmentation",
    "ocr",
    "visual_reasoning",
    "temporal_video",
]


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


class AuditQuestionControl(StrictModel):
    item_key: str = Field(min_length=1, max_length=180)
    evidence_modalities: tuple[EvidenceModality, ...] = Field(min_length=1, max_length=6)
    vision_contract: AuditVisionContract | None = None
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
        visual_allowed = "VISUAL" in self.evidence_modalities or "VIDEO" in self.evidence_modalities
        if self.vision_contract is not None and not visual_allowed:
            raise ValueError("vision_contract requires VISUAL or VIDEO evidence modality")
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
