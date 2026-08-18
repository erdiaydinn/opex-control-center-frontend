"""Identity-bound voice + gaze + gesture fusion for Jarvis spatial control.

This module resolves multimodal *local UI intent*. It does not execute OS or
business actions. Gaze is only a referent signal; a move requires a stable gaze
focus plus an explicit verified voice spatial command and/or an explicit hand
gesture. When voice and gesture both provide direction they must agree.

Free-text parsing is deliberately outside this contract. A voice command can be
constructed only from an identity-verified FINAL ``VoiceEvent`` and contains a
structured command chosen by an upstream, governed intent resolver. This keeps
partial ASR text, raw transcripts and model guesses from directly becoming
spatial authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .spatial_gaze import GazeFocusIntent
from .spatial_interaction import SpatialGestureCommand, SpatialGestureIntent
from .voice_session import VoiceEvent

SPATIAL_MULTIMODAL_FUSION_CONTRACT = "eay-spatial-multimodal-fusion-v1"


class SpatialFusionCommand(str, Enum):
    MOVE_FOCUSED_WINDOW_LEFT = "move_focused_window_left"
    MOVE_FOCUSED_WINDOW_RIGHT = "move_focused_window_right"
    CANCEL = "cancel"


class SpatialModality(str, Enum):
    VOICE = "voice"
    GAZE = "gaze"
    GESTURE = "gesture"


class VoiceSpatialCommand(BaseModel):
    contract: str = SPATIAL_MULTIMODAL_FUSION_CONTRACT
    voice_session_id: str = Field(min_length=1)
    spatial_session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    voice_event_id: str = Field(min_length=1)
    transcript_ref: str = Field(min_length=1)
    emitted_at: datetime
    command: SpatialFusionCommand
    raw_transcript_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def voice_command_is_structured_and_safe(self) -> "VoiceSpatialCommand":
        if self.emitted_at.tzinfo is None or self.emitted_at.utcoffset() is None:
            raise ValueError("spatial_fusion_voice_command_requires_timezone")
        if self.raw_transcript_retained:
            raise ValueError("spatial_fusion_cannot_retain_raw_voice_transcript")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_fusion_voice_never_authorizes_business_side_effects")
        return self


class SpatialFusionSession(BaseModel):
    spatial_session_id: str = Field(min_length=1)
    voice_session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    armed_at: datetime
    expires_at: datetime
    max_temporal_skew_ms: int = Field(default=1200, ge=100, le=5000)
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def session_is_short_lived_and_non_authorizing(self) -> "SpatialFusionSession":
        for value in (self.armed_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("spatial_fusion_session_requires_timezone")
        if self.expires_at <= self.armed_at:
            raise ValueError("spatial_fusion_session_expiry_invalid")
        if self.expires_at - self.armed_at > timedelta(minutes=30):
            raise ValueError("spatial_fusion_session_too_long")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_fusion_session_never_authorizes_business_side_effects")
        return self


class SpatialFusionIntent(BaseModel):
    contract: str = SPATIAL_MULTIMODAL_FUSION_CONTRACT
    spatial_session_id: str
    principal_ref: str
    identity_evidence_ref: str
    command: SpatialFusionCommand
    target_ref: str | None = None
    emitted_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    modalities: tuple[SpatialModality, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    local_ui_only: bool = True
    target_binding_required_before_execution: bool = True
    click_authorized: bool = False
    business_side_effects_authorized: bool = False
    raw_sensor_data_retained: bool = False

    @model_validator(mode="after")
    def intent_is_local_ui_proposal_only(self) -> "SpatialFusionIntent":
        if self.command is SpatialFusionCommand.CANCEL:
            if self.target_ref is not None:
                raise ValueError("spatial_fusion_cancel_cannot_target_object")
        elif not self.target_ref:
            raise ValueError("spatial_fusion_move_requires_focused_target")
        if not self.local_ui_only or not self.target_binding_required_before_execution:
            raise ValueError("spatial_fusion_intent_requires_local_target_binding")
        if self.click_authorized or self.business_side_effects_authorized:
            raise ValueError("spatial_fusion_intent_never_authorizes_actions")
        if self.raw_sensor_data_retained:
            raise ValueError("spatial_fusion_intent_cannot_retain_raw_sensor_data")
        if len(set(self.modalities)) != len(self.modalities):
            raise ValueError("spatial_fusion_modalities_must_be_unique")
        return self


class SpatialFusionDecision(BaseModel):
    contract: str = SPATIAL_MULTIMODAL_FUSION_CONTRACT
    intent: SpatialFusionIntent | None = None
    blockers: tuple[str, ...] = ()
    action_execution_authorized: bool = False

    @model_validator(mode="after")
    def decision_never_becomes_execution_authority(self) -> "SpatialFusionDecision":
        if self.action_execution_authorized:
            raise ValueError("spatial_fusion_decision_never_authorizes_execution")
        if self.intent is not None and self.blockers:
            raise ValueError("spatial_fusion_cannot_emit_intent_with_blockers")
        return self


def voice_event_to_spatial_command(
    *,
    event: VoiceEvent,
    spatial_session_id: str,
    command: SpatialFusionCommand,
) -> VoiceSpatialCommand:
    """Bind a structured spatial command to one verified final voice event."""

    if not event.intent_eligible:
        raise ValueError("spatial_fusion_voice_event_not_intent_eligible")
    assert event.principal_ref is not None
    assert event.identity_evidence_ref is not None
    assert event.transcript_ref is not None
    return VoiceSpatialCommand(
        voice_session_id=event.session_id,
        spatial_session_id=spatial_session_id,
        principal_ref=event.principal_ref,
        identity_evidence_ref=event.identity_evidence_ref,
        voice_event_id=event.event_id,
        transcript_ref=event.transcript_ref,
        emitted_at=event.occurred_at,
        command=command,
    )


def _gesture_direction(intent: SpatialGestureIntent) -> SpatialFusionCommand | None:
    if intent.command is SpatialGestureCommand.MOVE_ACTIVE_WINDOW_LEFT:
        return SpatialFusionCommand.MOVE_FOCUSED_WINDOW_LEFT
    if intent.command is SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT:
        return SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT
    return None


def _in_window(session: SpatialFusionSession, at: datetime) -> bool:
    return session.armed_at <= at <= session.expires_at


def fuse_spatial_modalities(
    *,
    session: SpatialFusionSession,
    voice: VoiceSpatialCommand | None = None,
    gaze: GazeFocusIntent | None = None,
    gesture: SpatialGestureIntent | None = None,
) -> SpatialFusionDecision:
    """Fuse signals into a non-executable local UI intent proposal."""

    blockers: list[str] = []
    times: list[datetime] = []
    evidence_refs: list[str] = []
    modalities: list[SpatialModality] = []

    if voice is not None:
        modalities.append(SpatialModality.VOICE)
        times.append(voice.emitted_at)
        evidence_refs.append(f"voice-event://{voice.voice_event_id}")
        evidence_refs.append(voice.transcript_ref)
        if voice.voice_session_id != session.voice_session_id:
            blockers.append("spatial_fusion_voice_session_mismatch")
        if voice.spatial_session_id != session.spatial_session_id:
            blockers.append("spatial_fusion_voice_spatial_session_mismatch")
        if voice.principal_ref != session.principal_ref:
            blockers.append("spatial_fusion_voice_principal_mismatch")
        if voice.identity_evidence_ref != session.identity_evidence_ref:
            blockers.append("spatial_fusion_voice_identity_mismatch")
        if not _in_window(session, voice.emitted_at):
            blockers.append("spatial_fusion_voice_outside_session_window")

    if gaze is not None:
        modalities.append(SpatialModality.GAZE)
        times.append(gaze.focused_at)
        evidence_refs.append(gaze.source_evidence_ref)
        if gaze.spatial_session_id != session.spatial_session_id:
            blockers.append("spatial_fusion_gaze_session_mismatch")
        if gaze.principal_ref != session.principal_ref:
            blockers.append("spatial_fusion_gaze_principal_mismatch")
        if gaze.identity_evidence_ref != session.identity_evidence_ref:
            blockers.append("spatial_fusion_gaze_identity_mismatch")
        if not _in_window(session, gaze.focused_at):
            blockers.append("spatial_fusion_gaze_outside_session_window")

    if gesture is not None:
        modalities.append(SpatialModality.GESTURE)
        times.append(gesture.emitted_at)
        evidence_refs.append(gesture.source_evidence_ref)
        if gesture.session_id != session.spatial_session_id:
            blockers.append("spatial_fusion_gesture_session_mismatch")
        if gesture.principal_ref != session.principal_ref:
            blockers.append("spatial_fusion_gesture_principal_mismatch")
        if not _in_window(session, gesture.emitted_at):
            blockers.append("spatial_fusion_gesture_outside_session_window")

    if not modalities:
        blockers.append("spatial_fusion_signal_missing")
        return SpatialFusionDecision(blockers=tuple(blockers))

    if len(times) >= 2:
        skew_ms = int((max(times) - min(times)).total_seconds() * 1000)
        if skew_ms > session.max_temporal_skew_ms:
            blockers.append("spatial_fusion_temporal_skew_exceeded")

    # Cancel is deliberately easy and safe. A verified voice cancellation can
    # stop a spatial proposal without gaze. Gesture cancellation may be added by
    # the hand recognizer but is not assumed here until that command exists.
    if voice is not None and voice.command is SpatialFusionCommand.CANCEL:
        if blockers:
            return SpatialFusionDecision(blockers=tuple(dict.fromkeys(blockers)))
        return SpatialFusionDecision(
            intent=SpatialFusionIntent(
                spatial_session_id=session.spatial_session_id,
                principal_ref=session.principal_ref,
                identity_evidence_ref=session.identity_evidence_ref,
                command=SpatialFusionCommand.CANCEL,
                emitted_at=max(times),
                confidence=1.0,
                modalities=tuple(modalities),
                evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            )
        )

    # Movement through the fusion layer always requires a gaze referent and at
    # least one explicit directional signal. Gaze alone cannot move anything.
    if gaze is None:
        blockers.append("spatial_fusion_move_requires_gaze_focus")
    if voice is None and gesture is None:
        blockers.append("spatial_fusion_move_requires_voice_or_gesture")

    voice_direction = (
        voice.command
        if voice is not None
        and voice.command
        in {
            SpatialFusionCommand.MOVE_FOCUSED_WINDOW_LEFT,
            SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT,
        }
        else None
    )
    gesture_direction = _gesture_direction(gesture) if gesture is not None else None

    if voice is not None and voice.command is not SpatialFusionCommand.CANCEL and voice_direction is None:
        blockers.append("spatial_fusion_voice_direction_unsupported")
    if gesture is not None and gesture_direction is None:
        blockers.append("spatial_fusion_gesture_direction_unsupported")
    if voice_direction is not None and gesture_direction is not None and voice_direction is not gesture_direction:
        blockers.append("spatial_fusion_direction_conflict")

    direction = voice_direction or gesture_direction
    if direction is None:
        blockers.append("spatial_fusion_direction_missing")

    if blockers:
        return SpatialFusionDecision(blockers=tuple(dict.fromkeys(blockers)))

    assert gaze is not None and direction is not None
    confidence_parts = [gaze.confidence]
    if gesture is not None:
        confidence_parts.append(gesture.confidence)
    # A verified structured voice command is identity-evidence bound rather than
    # probabilistic, so it contributes certainty 1.0 to the local intent vote.
    if voice is not None:
        confidence_parts.append(1.0)
    confidence = sum(confidence_parts) / len(confidence_parts)

    return SpatialFusionDecision(
        intent=SpatialFusionIntent(
            spatial_session_id=session.spatial_session_id,
            principal_ref=session.principal_ref,
            identity_evidence_ref=session.identity_evidence_ref,
            command=direction,
            target_ref=gaze.target_ref,
            emitted_at=max(times),
            confidence=min(1.0, max(0.0, confidence)),
            modalities=tuple(modalities),
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        )
    )
