"""Privacy-bound ambient desktop intelligence for Jarvis.

Ambient context is opt-in and ephemeral. Jarvis may derive short-lived semantic
signals from system audio, screen, microphone, or camera adapters, but this
layer never retains raw media and never converts passive observation into
business-action authority. Ambient rules can surface a notification or context
candidate; execution still goes through normal EAY authorization/capability
boundaries.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

AMBIENT_CONTEXT_CONTRACT = "eay-ambient-context-v1"


class AmbientModality(str, Enum):
    SYSTEM_AUDIO = "system_audio"
    SCREEN = "screen"
    MICROPHONE = "microphone"
    CAMERA = "camera"


class AmbientAction(str, Enum):
    NOTIFY = "notify"
    CONTEXT_CANDIDATE = "context_candidate"


class AmbientPrivacyPolicy(BaseModel):
    enabled_modalities: frozenset[AmbientModality] = frozenset()
    allowed_application_refs: frozenset[str] = frozenset()
    blocked_application_refs: frozenset[str] = frozenset()
    maximum_observation_seconds: int = Field(default=15, ge=1, le=60)
    local_processing_required: bool = True
    raw_media_retention_allowed: bool = False
    raw_transcript_retention_allowed: bool = False
    passive_observation_grants_authority: bool = False

    @model_validator(mode="after")
    def privacy_boundary_is_strict(self) -> "AmbientPrivacyPolicy":
        if self.raw_media_retention_allowed:
            raise ValueError("ambient_raw_media_retention_forbidden")
        if self.raw_transcript_retention_allowed:
            raise ValueError("ambient_raw_transcript_retention_forbidden")
        if self.passive_observation_grants_authority:
            raise ValueError("ambient_observation_never_grants_authority")
        overlap = self.allowed_application_refs & self.blocked_application_refs
        if overlap:
            raise ValueError("ambient_application_policy_conflict")
        return self


class AmbientSemanticSignal(BaseModel):
    contract: str = AMBIENT_CONTEXT_CONTRACT
    signal_ref: str = Field(min_length=1)
    modality: AmbientModality
    observed_at: datetime
    application_ref: str | None = None
    semantic_tags: frozenset[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    observation_seconds: float = Field(gt=0.0, le=60.0)
    local_processing: bool = True
    content_ref: str | None = None
    raw_media_retained: bool = False
    raw_transcript_retained: bool = False
    instruction_from_observation: bool = False

    @model_validator(mode="after")
    def signal_is_content_safe(self) -> "AmbientSemanticSignal":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("ambient_signal_requires_timezone")
        if self.raw_media_retained or self.raw_transcript_retained:
            raise ValueError("ambient_signal_cannot_retain_raw_content")
        if self.instruction_from_observation:
            raise ValueError("ambient_observation_is_data_not_instruction")
        return self


class AmbientWatchRule(BaseModel):
    rule_ref: str = Field(min_length=1)
    modalities: frozenset[AmbientModality] = Field(min_length=1)
    required_tags: frozenset[str] = Field(min_length=1)
    application_refs: frozenset[str] = frozenset()
    minimum_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    action: AmbientAction = AmbientAction.NOTIFY
    valid_from: datetime
    valid_until: datetime

    @model_validator(mode="after")
    def rule_is_time_bounded(self) -> "AmbientWatchRule":
        for value in (self.valid_from, self.valid_until):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("ambient_rule_requires_timezone")
        if self.valid_until <= self.valid_from:
            raise ValueError("ambient_rule_expiry_invalid")
        if self.valid_until - self.valid_from > timedelta(days=7):
            raise ValueError("ambient_rule_window_too_long")
        return self


class AmbientWatchDecision(BaseModel):
    contract: str = AMBIENT_CONTEXT_CONTRACT
    rule_ref: str
    signal_ref: str
    matched: bool
    action: AmbientAction | None = None
    blockers: tuple[str, ...] = ()
    notification_eligible: bool = False
    external_write_eligible: bool = False
    execution_authority_granted: bool = False
    raw_content_retained: bool = False

    @model_validator(mode="after")
    def decision_is_non_authoritative(self) -> "AmbientWatchDecision":
        if self.external_write_eligible or self.execution_authority_granted:
            raise ValueError("ambient_watch_cannot_authorize_external_write")
        if self.raw_content_retained:
            raise ValueError("ambient_watch_cannot_retain_raw_content")
        if self.matched and self.blockers:
            raise ValueError("ambient_watch_match_cannot_have_blockers")
        return self


def evaluate_ambient_watch(
    *,
    signal: AmbientSemanticSignal,
    rule: AmbientWatchRule,
    policy: AmbientPrivacyPolicy,
    now: datetime,
) -> AmbientWatchDecision:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("ambient_watch_requires_timezone")

    blockers: list[str] = []
    if signal.modality not in policy.enabled_modalities:
        blockers.append("ambient_modality_not_enabled")
    if signal.modality not in rule.modalities:
        blockers.append("ambient_rule_modality_mismatch")
    if not (rule.valid_from <= now <= rule.valid_until):
        blockers.append("ambient_rule_not_active")
    if signal.observation_seconds > policy.maximum_observation_seconds:
        blockers.append("ambient_observation_window_exceeded")
    if policy.local_processing_required and not signal.local_processing:
        blockers.append("ambient_local_processing_required")
    if signal.confidence < rule.minimum_confidence:
        blockers.append("ambient_signal_confidence_low")

    if signal.application_ref:
        if signal.application_ref in policy.blocked_application_refs:
            blockers.append("ambient_application_blocked")
        if policy.allowed_application_refs and signal.application_ref not in policy.allowed_application_refs:
            blockers.append("ambient_application_not_allowed")
        if rule.application_refs and signal.application_ref not in rule.application_refs:
            blockers.append("ambient_rule_application_mismatch")
    elif rule.application_refs:
        blockers.append("ambient_application_context_required")

    missing_tags = {tag.casefold() for tag in rule.required_tags} - {
        tag.casefold() for tag in signal.semantic_tags
    }
    if missing_tags:
        blockers.append("ambient_required_semantic_tag_missing")

    matched = not blockers
    return AmbientWatchDecision(
        rule_ref=rule.rule_ref,
        signal_ref=signal.signal_ref,
        matched=matched,
        action=rule.action if matched else None,
        blockers=tuple(dict.fromkeys(blockers)),
        notification_eligible=matched and rule.action is AmbientAction.NOTIFY,
    )
