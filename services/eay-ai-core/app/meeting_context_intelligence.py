"""Local, privacy-bound meeting intelligence for Jarvis.

Speaker diarization is context, never identity or authority. This layer accepts
only semantic/diarization observations with raw audio, transcripts and
voiceprints already discarded. It may create notification/context candidates,
but it cannot create tasks, approve actions or authenticate a principal.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .ambient_context_intelligence import AmbientModality, AmbientSemanticSignal

MEETING_CONTEXT_CONTRACT = "eay-meeting-context-v1"


class MeetingMomentKind(str, Enum):
    TOPIC_MENTION = "topic_mention"
    DECISION_CANDIDATE = "decision_candidate"
    ACTION_ITEM_CANDIDATE = "action_item_candidate"
    RISK_MENTION = "risk_mention"


class MeetingContextPolicy(BaseModel):
    enabled: bool = False
    local_processing_required: bool = True
    diarization_allowed: bool = True
    speaker_identity_resolution_allowed: bool = False
    voice_biometric_authority_allowed: bool = False
    raw_audio_retention_allowed: bool = False
    raw_transcript_retention_allowed: bool = False
    voiceprint_retention_allowed: bool = False
    maximum_segment_seconds: float = Field(default=30.0, gt=0.0, le=60.0)
    maximum_signal_skew_seconds: float = Field(default=5.0, ge=0.0, le=30.0)

    @model_validator(mode="after")
    def privacy_boundary_is_strict(self) -> "MeetingContextPolicy":
        if self.speaker_identity_resolution_allowed:
            raise ValueError("meeting_speaker_identity_resolution_forbidden")
        if self.voice_biometric_authority_allowed:
            raise ValueError("meeting_voice_biometric_authority_forbidden")
        if self.raw_audio_retention_allowed:
            raise ValueError("meeting_raw_audio_retention_forbidden")
        if self.raw_transcript_retention_allowed:
            raise ValueError("meeting_raw_transcript_retention_forbidden")
        if self.voiceprint_retention_allowed:
            raise ValueError("meeting_voiceprint_retention_forbidden")
        return self


class MeetingDiarizationSignal(BaseModel):
    contract: str = MEETING_CONTEXT_CONTRACT
    meeting_ref: str = Field(min_length=1)
    session_ref: str = Field(min_length=1)
    speaker_cluster_ref: str = Field(min_length=1)
    observed_at: datetime
    segment_seconds: float = Field(gt=0.0, le=60.0)
    diarization_confidence: float = Field(ge=0.0, le=1.0)
    semantic_tags: frozenset[str] = Field(min_length=1)
    topic_refs: frozenset[str] = frozenset()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    local_processing: bool = True
    raw_audio_retained: bool = False
    raw_transcript_retained: bool = False
    voiceprint_retained: bool = False
    speaker_identity_claimed: bool = False
    identity_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def signal_is_non_identifying(self) -> "MeetingDiarizationSignal":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("meeting_signal_requires_timezone")
        if self.raw_audio_retained or self.raw_transcript_retained or self.voiceprint_retained:
            raise ValueError("meeting_signal_cannot_retain_raw_voice_material")
        if self.speaker_identity_claimed:
            raise ValueError("meeting_diarization_cluster_is_not_identity")
        if self.identity_authority_granted or self.execution_authority_granted:
            raise ValueError("meeting_signal_never_grants_authority")
        return self


class MeetingContextCandidate(BaseModel):
    contract: str = MEETING_CONTEXT_CONTRACT
    candidate_ref: str = Field(min_length=1)
    meeting_ref: str = Field(min_length=1)
    session_ref: str = Field(min_length=1)
    speaker_cluster_ref: str = Field(min_length=1)
    kind: MeetingMomentKind
    observed_at: datetime
    semantic_tags: frozenset[str] = Field(min_length=1)
    topic_refs: frozenset[str] = frozenset()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    notification_eligible: bool = True
    task_creation_allowed: bool = False
    speaker_identity_resolved: bool = False
    identity_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def candidate_remains_context_only(self) -> "MeetingContextCandidate":
        if self.task_creation_allowed:
            raise ValueError("meeting_candidate_cannot_create_task")
        if self.speaker_identity_resolved:
            raise ValueError("meeting_candidate_cannot_resolve_speaker_identity")
        if self.identity_authority_granted or self.execution_authority_granted:
            raise ValueError("meeting_candidate_never_grants_authority")
        return self


class MeetingWatchRule(BaseModel):
    rule_ref: str = Field(min_length=1)
    meeting_refs: frozenset[str] = frozenset()
    required_tags: frozenset[str] = Field(min_length=1)
    required_topic_refs: frozenset[str] = frozenset()
    minimum_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    valid_from: datetime
    valid_until: datetime

    @model_validator(mode="after")
    def rule_is_bounded(self) -> "MeetingWatchRule":
        for value in (self.valid_from, self.valid_until):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("meeting_watch_rule_requires_timezone")
        if self.valid_until <= self.valid_from:
            raise ValueError("meeting_watch_rule_expiry_invalid")
        if self.valid_until - self.valid_from > timedelta(hours=12):
            raise ValueError("meeting_watch_rule_window_too_long")
        return self


class MeetingWatchDecision(BaseModel):
    contract: str = MEETING_CONTEXT_CONTRACT
    rule_ref: str
    candidate_ref: str
    matched: bool
    blockers: tuple[str, ...] = ()
    notification_eligible: bool = False
    task_creation_allowed: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def decision_is_non_authoritative(self) -> "MeetingWatchDecision":
        if self.task_creation_allowed or self.execution_authority_granted:
            raise ValueError("meeting_watch_never_authorizes_action")
        if self.matched and self.blockers:
            raise ValueError("meeting_watch_match_cannot_have_blockers")
        return self


def meeting_signal_from_ambient(
    *,
    ambient: AmbientSemanticSignal,
    meeting_ref: str,
    session_ref: str,
    speaker_cluster_ref: str,
    diarization_confidence: float,
    topic_refs: frozenset[str] = frozenset(),
    evidence_refs: tuple[str, ...] = (),
) -> MeetingDiarizationSignal:
    if ambient.modality not in {AmbientModality.MICROPHONE, AmbientModality.SYSTEM_AUDIO}:
        raise ValueError("meeting_context_requires_audio_modality")
    if not ambient.local_processing:
        raise ValueError("meeting_context_requires_local_processing")
    if ambient.instruction_from_observation:
        raise ValueError("meeting_observation_is_data_not_instruction")
    refs = tuple(dict.fromkeys((*evidence_refs, *( (() if ambient.content_ref is None else (ambient.content_ref,)) ))))
    if not refs:
        refs = (ambient.signal_ref,)
    return MeetingDiarizationSignal(
        meeting_ref=meeting_ref,
        session_ref=session_ref,
        speaker_cluster_ref=speaker_cluster_ref,
        observed_at=ambient.observed_at,
        segment_seconds=ambient.observation_seconds,
        diarization_confidence=diarization_confidence,
        semantic_tags=ambient.semantic_tags,
        topic_refs=topic_refs,
        evidence_refs=refs,
        local_processing=ambient.local_processing,
    )


def _candidate_kind(tags: frozenset[str]) -> MeetingMomentKind:
    normalized = {item.casefold() for item in tags}
    if "decision_candidate" in normalized:
        return MeetingMomentKind.DECISION_CANDIDATE
    if "action_item_candidate" in normalized:
        return MeetingMomentKind.ACTION_ITEM_CANDIDATE
    if "risk" in normalized or "risk_mention" in normalized:
        return MeetingMomentKind.RISK_MENTION
    return MeetingMomentKind.TOPIC_MENTION


def derive_meeting_candidate(
    *,
    signal: MeetingDiarizationSignal,
    policy: MeetingContextPolicy,
) -> MeetingContextCandidate:
    blockers: list[str] = []
    if not policy.enabled:
        blockers.append("meeting_context_disabled")
    if not policy.diarization_allowed:
        blockers.append("meeting_diarization_not_allowed")
    if policy.local_processing_required and not signal.local_processing:
        blockers.append("meeting_local_processing_required")
    if signal.segment_seconds > policy.maximum_segment_seconds:
        blockers.append("meeting_segment_window_exceeded")
    if blockers:
        raise ValueError(";".join(blockers))
    return MeetingContextCandidate(
        candidate_ref=f"meeting-candidate://{signal.meeting_ref}/{signal.session_ref}/{signal.speaker_cluster_ref}/{int(signal.observed_at.timestamp() * 1000)}",
        meeting_ref=signal.meeting_ref,
        session_ref=signal.session_ref,
        speaker_cluster_ref=signal.speaker_cluster_ref,
        kind=_candidate_kind(signal.semantic_tags),
        observed_at=signal.observed_at,
        semantic_tags=signal.semantic_tags,
        topic_refs=signal.topic_refs,
        evidence_refs=signal.evidence_refs,
        confidence=signal.diarization_confidence,
    )


def evaluate_meeting_watch(
    *,
    candidate: MeetingContextCandidate,
    rule: MeetingWatchRule,
    now: datetime,
) -> MeetingWatchDecision:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("meeting_watch_requires_timezone")
    blockers: list[str] = []
    if not (rule.valid_from <= now <= rule.valid_until):
        blockers.append("meeting_watch_rule_not_active")
    if rule.meeting_refs and candidate.meeting_ref not in rule.meeting_refs:
        blockers.append("meeting_watch_meeting_mismatch")
    if candidate.confidence < rule.minimum_confidence:
        blockers.append("meeting_watch_confidence_low")
    tags = {item.casefold() for item in candidate.semantic_tags}
    if {item.casefold() for item in rule.required_tags} - tags:
        blockers.append("meeting_watch_required_tag_missing")
    if rule.required_topic_refs - candidate.topic_refs:
        blockers.append("meeting_watch_required_topic_missing")
    matched = not blockers
    return MeetingWatchDecision(
        rule_ref=rule.rule_ref,
        candidate_ref=candidate.candidate_ref,
        matched=matched,
        blockers=tuple(dict.fromkeys(blockers)),
        notification_eligible=matched,
    )
