"""Hardened production wrapper for EAY local voice.

The base local voice contract intentionally exposes only opaque transcript refs,
but a deterministic content hash can still permit dictionary matching of common
short utterances. Production construction therefore uses an ephemeral random
HMAC key that is never serialized, audited or persisted. Repeated text across
runtime instances produces unlinkable transcript references.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from .local_voice_runtime import LocalVoiceRuntime

LOCAL_VOICE_PRIVACY_RUNTIME_CONTRACT = "eay-local-voice-privacy-runtime-v1"


class HardenedLocalVoiceRuntime(LocalVoiceRuntime):
    """LocalVoiceRuntime with process-ephemeral, unlinkable transcript refs."""

    def __init__(self, *args, transcript_hmac_key: bytes | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        key = transcript_hmac_key if transcript_hmac_key is not None else secrets.token_bytes(32)
        if len(key) < 32:
            raise ValueError("local_voice_transcript_hmac_key_too_short")
        self._transcript_hmac_key = bytes(key)

    def _transcript_ref(self, session_id: str, sequence: int, text: str) -> str:
        digest = hmac.new(
            self._transcript_hmac_key,
            f"{session_id}|{sequence}|{text}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"transcript://local-hmac/{digest}"

    def export_secret_state(self) -> None:
        """There is deliberately no serialization/export path for the HMAC key."""

        raise PermissionError("local_voice_ephemeral_secret_export_forbidden")
