"""Realtime conversational control state for Jarvis voice sessions.

This is transport/model agnostic: ASR/TTS providers may stream partial content,
but only a final, evidence-bound user identity plus final utterance can create
intent. Barge-in immediately stops assistant speech. A stop request during a
side-effecting execution becomes a halt request that still requires effect
verification; it never assumes an in-flight external write was rolled back.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

VOICE_SESSION_CONTRACT = "eay-realtime-voice-session-v1"


class VoiceSessionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    EXECUTING = "executing"
    HALTED = "halted"


class VoiceEventKind(str, Enum):
    WAKE = "wake"
    PARTIAL_UTTERANCE = "partial_utterance"
    FINAL_UTTERANCE = "final_utterance"
    ASSISTANT_SPEECH_STARTED = "assistant_speech_started"
    ASSISTANT_SPEECH_FINISHED = "assistant_speech_finished"
    BARGE_IN = "barge_in"
    STOP = "stop"
    CONTINUE = "continue"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_FINISHED = "execution_finished"


class VoiceEvent(BaseModel):
    event_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    occurred_at: datetime
    kind: VoiceEventKind
    principal_ref: str | None = None
    transcript_ref: str | None = None
    identity_verified: bool = False
    identity_evidence_ref: str | None = None
    mission_ref: str | None = None
    side_effect_in_flight: bool = False

    @model_validator(mode="after")
    def event_contract(self) -> "VoiceEvent":
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("voice_event_requires_timezone")
        if self.kind in {VoiceEventKind.PARTIAL_UTTERANCE, VoiceEventKind.FINAL_UTTERANCE} and not self.transcript_ref:
            raise ValueError("voice_utterance_requires_transcript_ref")
        if self.kind is VoiceEventKind.FINAL_UTTERANCE and not self.principal_ref:
            raise ValueError("voice_final_utterance_requires_principal")
        if self.identity_verified:
            if not self.principal_ref:
                raise ValueError("voice_verified_identity_requires_principal")
            if not self.identity_evidence_ref:
                raise ValueError("voice_verified_identity_requires_evidence")
        return self

    @property
    def intent_eligible(self) -> bool:
        return (
            self.kind is VoiceEventKind.FINAL_UTTERANCE
            and self.identity_verified
            and bool(self.identity_evidence_ref)
            and bool(self.principal_ref)
            and bool(self.transcript_ref)
        )


class VoiceSession(BaseModel):
    contract: str = VOICE_SESSION_CONTRACT
    session_id: str
    state: VoiceSessionState = VoiceSessionState.IDLE
    active_principal_ref: str | None = None
    active_mission_ref: str | None = None
    last_final_utterance_ref: str | None = None
    assistant_speech_cancel_requested: bool = False
    mission_halt_requested: bool = False
    effect_verification_required: bool = False
    event_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()


class VoiceTransition(BaseModel):
    contract: str = VOICE_SESSION_CONTRACT
    before: VoiceSessionState
    after: VoiceSessionState
    event_id: str
    intent_accepted: bool = False
    assistant_speech_cancel_requested: bool = False
    mission_halt_requested: bool = False
    effect_verification_required: bool = False
    blockers: tuple[str, ...] = ()


def new_voice_session(session_id: str) -> VoiceSession:
    if not session_id.strip():
        raise ValueError("voice_session_id_required")
    return VoiceSession(session_id=session_id)


def apply_voice_event(session: VoiceSession, event: VoiceEvent) -> tuple[VoiceSession, VoiceTransition]:
    if event.session_id != session.session_id:
        raise ValueError("voice_event_session_mismatch")
    if event.event_id in session.event_ids:
        raise ValueError("voice_event_duplicate")

    before = session.state
    after = before
    blockers: list[str] = []
    intent_accepted = False
    cancel_speech = session.assistant_speech_cancel_requested
    halt_requested = session.mission_halt_requested
    verify_effect = session.effect_verification_required
    principal = session.active_principal_ref
    mission_ref = event.mission_ref or session.active_mission_ref
    last_final = session.last_final_utterance_ref

    if event.kind is VoiceEventKind.WAKE:
        after = VoiceSessionState.LISTENING
        if event.identity_verified and event.principal_ref and event.identity_evidence_ref:
            principal = event.principal_ref
    elif event.kind is VoiceEventKind.PARTIAL_UTTERANCE:
        after = VoiceSessionState.LISTENING
        blockers.append("voice_partial_transcript_not_intent_eligible")
    elif event.kind is VoiceEventKind.FINAL_UTTERANCE:
        if not event.intent_eligible:
            after = VoiceSessionState.LISTENING
            blockers.append("voice_final_utterance_identity_not_verified")
        elif principal is not None and principal != event.principal_ref:
            after = VoiceSessionState.LISTENING
            blockers.append("voice_principal_changed_mid_session")
        else:
            principal = event.principal_ref
            last_final = event.transcript_ref
            after = VoiceSessionState.THINKING
            intent_accepted = True
    elif event.kind is VoiceEventKind.ASSISTANT_SPEECH_STARTED:
        after = VoiceSessionState.SPEAKING
        cancel_speech = False
    elif event.kind is VoiceEventKind.ASSISTANT_SPEECH_FINISHED:
        after = VoiceSessionState.LISTENING
        cancel_speech = False
    elif event.kind is VoiceEventKind.BARGE_IN:
        cancel_speech = True
        after = VoiceSessionState.LISTENING
    elif event.kind is VoiceEventKind.STOP:
        cancel_speech = True
        halt_requested = True
        after = VoiceSessionState.HALTED
        if before is VoiceSessionState.EXECUTING or event.side_effect_in_flight:
            verify_effect = True
            blockers.append("voice_stop_during_execution_requires_effect_verification")
    elif event.kind is VoiceEventKind.CONTINUE:
        if verify_effect:
            blockers.append("voice_continue_blocked_pending_effect_verification")
            after = VoiceSessionState.HALTED
        else:
            halt_requested = False
            after = VoiceSessionState.LISTENING
    elif event.kind is VoiceEventKind.EXECUTION_STARTED:
        after = VoiceSessionState.EXECUTING
        mission_ref = event.mission_ref or mission_ref
    elif event.kind is VoiceEventKind.EXECUTION_FINISHED:
        after = VoiceSessionState.LISTENING
        verify_effect = False
        halt_requested = False

    updated = session.model_copy(
        update={
            "state": after,
            "active_principal_ref": principal,
            "active_mission_ref": mission_ref,
            "last_final_utterance_ref": last_final,
            "assistant_speech_cancel_requested": cancel_speech,
            "mission_halt_requested": halt_requested,
            "effect_verification_required": verify_effect,
            "event_ids": (*session.event_ids, event.event_id),
            "blockers": tuple(dict.fromkeys(blockers)),
        }
    )
    return updated, VoiceTransition(
        before=before,
        after=after,
        event_id=event.event_id,
        intent_accepted=intent_accepted,
        assistant_speech_cancel_requested=cancel_speech,
        mission_halt_requested=halt_requested,
        effect_verification_required=verify_effect,
        blockers=tuple(dict.fromkeys(blockers)),
    )
