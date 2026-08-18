"""Trusted wake/presence gate for Jarvis local voice.

Wake-word detection is convenience, never identity. A final local transcript can
enter VoiceSession as an intent only when a trusted local identity artifact is
valid. The default identity sources are authenticated OS session or corporate
OIDC; voice biometrics are explicitly outside this contract.

While sleeping, an exact wake alias must prefix the final utterance. After a
successful wake, a short conversational window allows follow-up turns without
repeating the wake word, while re-checking the same trusted identity on every
turn. Raw transcript/command text remains transient and never appears in the
serializable receipt.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .local_voice_recognizer import LocalRecognitionReceipt
from .local_voice_runtime import TransientTranscript
from .voice_session import (
    VoiceEvent,
    VoiceEventKind,
    VoiceSession,
    VoiceSessionState,
    apply_voice_event,
)

LOCAL_VOICE_PRESENCE_CONTRACT = "eay-local-voice-presence-v1"


class LocalIdentitySource(str, Enum):
    OS_SESSION = "os_session"
    CORPORATE_OIDC = "corporate_oidc"


class TrustedLocalVoiceIdentity(BaseModel):
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    local_device_ref: str = Field(min_length=1)
    source: LocalIdentitySource
    authenticated_at: datetime
    expires_at: datetime
    biometric_voice_identity_used: bool = False
    raw_credential_material_retained: bool = False

    @model_validator(mode="after")
    def identity_is_bounded_and_non_biometric(self) -> "TrustedLocalVoiceIdentity":
        for value in (self.authenticated_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("local_voice_identity_requires_timezone")
        if self.expires_at <= self.authenticated_at:
            raise ValueError("local_voice_identity_expiry_invalid")
        if self.expires_at - self.authenticated_at > timedelta(hours=12):
            raise ValueError("local_voice_identity_window_too_long")
        if self.biometric_voice_identity_used:
            raise ValueError("local_voice_presence_does_not_use_voice_biometrics")
        if self.raw_credential_material_retained:
            raise ValueError("local_voice_identity_cannot_retain_credentials")
        return self

    def valid_at(self, now: datetime) -> bool:
        return self.authenticated_at <= now <= self.expires_at


class WakePolicy(BaseModel):
    wake_aliases: tuple[str, ...] = ("jarvis",)
    conversational_window_seconds: int = Field(default=120, ge=10, le=300)
    wake_required_when_sleeping: bool = True
    wake_word_grants_authority: bool = False

    @model_validator(mode="after")
    def wake_policy_is_safe(self) -> "WakePolicy":
        normalized = tuple(_normalize(alias) for alias in self.wake_aliases)
        if not normalized or any(not alias for alias in normalized):
            raise ValueError("local_voice_wake_alias_required")
        if len(normalized) != len(set(normalized)):
            raise ValueError("local_voice_wake_alias_duplicate")
        if self.wake_word_grants_authority:
            raise ValueError("local_voice_wake_word_never_grants_authority")
        return self


class VoicePresenceState(BaseModel):
    contract: str = LOCAL_VOICE_PRESENCE_CONTRACT
    voice_session_id: str = Field(min_length=1)
    awake_until: datetime | None = None
    last_identity_evidence_ref: str | None = None
    wake_count: int = Field(default=0, ge=0)
    accepted_turn_count: int = Field(default=0, ge=0)
    raw_transcript_retained: bool = False

    @model_validator(mode="after")
    def state_is_content_free(self) -> "VoicePresenceState":
        if self.raw_transcript_retained:
            raise ValueError("local_voice_presence_cannot_retain_transcript")
        return self

    def awake_at(self, now: datetime) -> bool:
        return self.awake_until is not None and now <= self.awake_until


@dataclass(frozen=True)
class TransientVoiceCommand:
    text: str = field(repr=False)
    command_ref: str
    transcript_ref: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("local_voice_presence_command_empty")


class VoicePresenceReceipt(BaseModel):
    contract: str = LOCAL_VOICE_PRESENCE_CONTRACT
    voice_session_id: str
    transcript_ref: str
    final: bool
    wake_detected: bool = False
    awake: bool = False
    command_eligible: bool = False
    command_ref: str | None = None
    voice_event_ids: tuple[str, ...] = ()
    voice_state: VoiceSessionState
    blockers: tuple[str, ...] = ()
    raw_transcript_retained: bool = False
    command_text_retained: bool = False
    wake_word_authority: bool = False
    biometric_voice_identity_used: bool = False

    @model_validator(mode="after")
    def receipt_is_safe(self) -> "VoicePresenceReceipt":
        if self.command_eligible and not self.command_ref:
            raise ValueError("local_voice_presence_eligible_command_requires_ref")
        if self.raw_transcript_retained or self.command_text_retained:
            raise ValueError("local_voice_presence_receipt_cannot_retain_content")
        if self.wake_word_authority:
            raise ValueError("local_voice_wake_word_never_authorizes_command")
        if self.biometric_voice_identity_used:
            raise ValueError("local_voice_presence_receipt_cannot_claim_biometric_identity")
        return self


def _normalize(text: str) -> str:
    text = text.casefold().strip()
    text = re.sub(r"[^\wçğıöşü]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _wake_remainder(text: str, aliases: tuple[str, ...]) -> tuple[bool, str]:
    normalized = _normalize(text)
    for raw_alias in sorted(aliases, key=len, reverse=True):
        alias = _normalize(raw_alias)
        if normalized == alias:
            return True, ""
        prefix = f"{alias} "
        if normalized.startswith(prefix):
            return True, normalized[len(prefix):].strip()
    return False, normalized


class WakeGatedVoiceController:
    def __init__(
        self,
        *,
        session: VoiceSession,
        policy: WakePolicy | None = None,
        command_hmac_key: bytes | None = None,
    ) -> None:
        self.session = session
        self.policy = policy or WakePolicy()
        self.presence = VoicePresenceState(voice_session_id=session.session_id)
        key = command_hmac_key if command_hmac_key is not None else secrets.token_bytes(32)
        if len(key) < 32:
            raise ValueError("local_voice_presence_hmac_key_too_short")
        self._hmac_key = bytes(key)
        self._event_counter = 0

    def _event_id(self, kind: str) -> str:
        self._event_counter += 1
        return f"voice-presence:{self.session.session_id}:{kind}:{self._event_counter}"

    def _command_ref(self, transcript_ref: str, command_text: str) -> str:
        digest = hmac.new(
            self._hmac_key,
            f"{transcript_ref}|{command_text}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"voice-command://local/{digest}"

    def _apply(self, event: VoiceEvent) -> None:
        self.session, _ = apply_voice_event(self.session, event)

    def consume(
        self,
        *,
        transcript: TransientTranscript,
        recognition: LocalRecognitionReceipt,
        identity: TrustedLocalVoiceIdentity,
        occurred_at: datetime,
    ) -> tuple[TransientVoiceCommand | None, VoicePresenceReceipt]:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("local_voice_presence_turn_requires_timezone")
        if recognition.voice_session_id != self.session.session_id:
            raise ValueError("local_voice_presence_session_mismatch")
        if transcript.transcript_ref != recognition.transcript_ref:
            raise ValueError("local_voice_presence_transcript_ref_mismatch")
        if transcript.final != recognition.final:
            raise ValueError("local_voice_presence_finality_mismatch")

        event_ids: list[str] = []
        blockers: list[str] = []

        if not transcript.final:
            event_id = self._event_id("partial")
            self._apply(
                VoiceEvent(
                    event_id=event_id,
                    session_id=self.session.session_id,
                    occurred_at=occurred_at,
                    kind=VoiceEventKind.PARTIAL_UTTERANCE,
                    transcript_ref=transcript.transcript_ref,
                )
            )
            event_ids.append(event_id)
            blockers.append("local_voice_presence_partial_not_command_eligible")
            return None, VoicePresenceReceipt(
                voice_session_id=self.session.session_id,
                transcript_ref=transcript.transcript_ref,
                final=False,
                awake=self.presence.awake_at(occurred_at),
                voice_event_ids=tuple(event_ids),
                voice_state=self.session.state,
                blockers=tuple(blockers),
            )

        if not identity.valid_at(occurred_at):
            blockers.append("local_voice_presence_trusted_identity_expired")
            self.presence = self.presence.model_copy(update={"awake_until": None})
            return None, VoicePresenceReceipt(
                voice_session_id=self.session.session_id,
                transcript_ref=transcript.transcript_ref,
                final=True,
                awake=False,
                voice_state=self.session.state,
                blockers=tuple(blockers),
            )

        already_awake = self.presence.awake_at(occurred_at)
        wake_detected, remainder = _wake_remainder(transcript.text, self.policy.wake_aliases)
        command_text = transcript.text.strip() if already_awake else remainder

        if not already_awake:
            if self.policy.wake_required_when_sleeping and not wake_detected:
                blockers.append("local_voice_presence_wake_required")
                return None, VoicePresenceReceipt(
                    voice_session_id=self.session.session_id,
                    transcript_ref=transcript.transcript_ref,
                    final=True,
                    wake_detected=False,
                    awake=False,
                    voice_state=self.session.state,
                    blockers=tuple(blockers),
                )
            wake_event_id = self._event_id("wake")
            self._apply(
                VoiceEvent(
                    event_id=wake_event_id,
                    session_id=self.session.session_id,
                    occurred_at=occurred_at,
                    kind=VoiceEventKind.WAKE,
                    principal_ref=identity.principal_ref,
                    identity_verified=True,
                    identity_evidence_ref=identity.identity_evidence_ref,
                )
            )
            event_ids.append(wake_event_id)
            self.presence = self.presence.model_copy(
                update={
                    "awake_until": occurred_at + timedelta(seconds=self.policy.conversational_window_seconds),
                    "last_identity_evidence_ref": identity.identity_evidence_ref,
                    "wake_count": self.presence.wake_count + 1,
                }
            )
            if not command_text:
                return None, VoicePresenceReceipt(
                    voice_session_id=self.session.session_id,
                    transcript_ref=transcript.transcript_ref,
                    final=True,
                    wake_detected=True,
                    awake=True,
                    voice_event_ids=tuple(event_ids),
                    voice_state=self.session.state,
                )
        else:
            if self.presence.last_identity_evidence_ref != identity.identity_evidence_ref:
                blockers.append("local_voice_presence_identity_changed_during_window")
                self.presence = self.presence.model_copy(update={"awake_until": None})
                return None, VoicePresenceReceipt(
                    voice_session_id=self.session.session_id,
                    transcript_ref=transcript.transcript_ref,
                    final=True,
                    wake_detected=wake_detected,
                    awake=False,
                    voice_state=self.session.state,
                    blockers=tuple(blockers),
                )

        command_ref = self._command_ref(transcript.transcript_ref, command_text)
        final_event_id = self._event_id("final")
        self._apply(
            VoiceEvent(
                event_id=final_event_id,
                session_id=self.session.session_id,
                occurred_at=occurred_at,
                kind=VoiceEventKind.FINAL_UTTERANCE,
                principal_ref=identity.principal_ref,
                transcript_ref=transcript.transcript_ref,
                identity_verified=True,
                identity_evidence_ref=identity.identity_evidence_ref,
            )
        )
        event_ids.append(final_event_id)
        self.presence = self.presence.model_copy(
            update={
                "awake_until": occurred_at + timedelta(seconds=self.policy.conversational_window_seconds),
                "last_identity_evidence_ref": identity.identity_evidence_ref,
                "accepted_turn_count": self.presence.accepted_turn_count + 1,
            }
        )
        command = TransientVoiceCommand(
            text=command_text,
            command_ref=command_ref,
            transcript_ref=transcript.transcript_ref,
        )
        return command, VoicePresenceReceipt(
            voice_session_id=self.session.session_id,
            transcript_ref=transcript.transcript_ref,
            final=True,
            wake_detected=wake_detected,
            awake=True,
            command_eligible=True,
            command_ref=command_ref,
            voice_event_ids=tuple(event_ids),
            voice_state=self.session.state,
        )

    def sleep(self) -> None:
        self.presence = self.presence.model_copy(update={"awake_until": None})
