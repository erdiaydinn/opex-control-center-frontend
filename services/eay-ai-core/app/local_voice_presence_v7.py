"""Wake-text preserving production controller for Jarvis local voice v7.

The v5 presence controller intentionally normalized text to detect wake aliases.
That is safe for wake matching but can damage operational entities such as
Fulya, ÇarşıPortal, SKU/Order IDs, punctuation and user casing when a wake word
and command arrive in the same ASR final result.

This wrapper keeps v5's proven identity/wake/VoiceSession authority semantics,
but splits an exact wake prefix from the transient transcript before invoking
the v5 controller. The command remainder is preserved byte-for-byte apart from
outer whitespace. No transcript text is added to serializable receipts.
"""

from __future__ import annotations

import re

from .local_voice_presence import (
    TrustedLocalVoiceIdentity,
    TransientVoiceCommand,
    VoicePresenceReceipt,
    WakeGatedVoiceController,
)
from .local_voice_recognizer import LocalRecognitionReceipt
from .local_voice_runtime import TransientTranscript

LOCAL_VOICE_PRESENCE_V7_CONTRACT = "eay-local-voice-presence-v7"

_WAKE_SEPARATOR = r"[\s,;:!?.\-–—]+"


def _split_wake_prefix_preserving_text(
    text: str,
    aliases: tuple[str, ...],
) -> tuple[bool, str]:
    """Detect a leading wake alias while preserving the original remainder."""

    stripped = text.strip()
    for raw_alias in sorted(aliases, key=len, reverse=True):
        alias = raw_alias.strip()
        if not alias:
            continue
        pattern = re.compile(
            rf"^\s*{re.escape(alias)}(?=$|[\s,;:!?.\-–—])(?:{_WAKE_SEPARATOR})?(?P<remainder>.*)$",
            flags=re.IGNORECASE | re.UNICODE,
        )
        match = pattern.match(text)
        if match is not None:
            return True, match.group("remainder").strip()
    return False, stripped


class PreservingWakeGatedVoiceController(WakeGatedVoiceController):
    """v5 authority model with lossless transient command remainder handling."""

    def consume(
        self,
        *,
        transcript: TransientTranscript,
        recognition: LocalRecognitionReceipt,
        identity: TrustedLocalVoiceIdentity,
        occurred_at,
    ) -> tuple[TransientVoiceCommand | None, VoicePresenceReceipt]:
        # Partial results and already-awake follow-ups are handled unchanged by
        # the proven v5 controller. Follow-up text was already preserved there.
        if not transcript.final or self.presence.awake_at(occurred_at):
            return super().consume(
                transcript=transcript,
                recognition=recognition,
                identity=identity,
                occurred_at=occurred_at,
            )

        wake_detected, remainder = _split_wake_prefix_preserving_text(
            transcript.text,
            self.policy.wake_aliases,
        )
        if not wake_detected or not remainder:
            return super().consume(
                transcript=transcript,
                recognition=recognition,
                identity=identity,
                occurred_at=occurred_at,
            )

        # First feed a wake-only transient view through v5 so its exact trusted
        # identity + WAKE semantics remain the authority source. Same opaque
        # transcript ref is safe because event IDs are separately unique and no
        # raw text is persisted by VoiceSession.
        wake_view = TransientTranscript(
            text=self.policy.wake_aliases[0],
            transcript_ref=transcript.transcript_ref,
            language_code=transcript.language_code,
            confidence=transcript.confidence,
            final=True,
        )
        _, wake_receipt = super().consume(
            transcript=wake_view,
            recognition=recognition,
            identity=identity,
            occurred_at=occurred_at,
        )
        if not wake_receipt.awake or wake_receipt.blockers:
            return None, wake_receipt

        # Now v5 sees an already-awake session and therefore preserves the exact
        # transient remainder rather than normalizing it.
        command_view = TransientTranscript(
            text=remainder,
            transcript_ref=transcript.transcript_ref,
            language_code=transcript.language_code,
            confidence=transcript.confidence,
            final=True,
        )
        command, command_receipt = super().consume(
            transcript=command_view,
            recognition=recognition,
            identity=identity,
            occurred_at=occurred_at,
        )
        combined = command_receipt.model_copy(
            update={
                "wake_detected": True,
                "voice_event_ids": (*wake_receipt.voice_event_ids, *command_receipt.voice_event_ids),
            }
        )
        return command, combined
