from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .voice_streaming import AudioFrame


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class VoiceWakeInputProof:
    session_id: str
    language: str
    deployment_manifest_fingerprint: str
    wakeword_identity_fingerprint: str
    fingerprint: str


@dataclass(frozen=True)
class VoiceAudioFrameProof:
    session_id: str
    deployment_manifest_fingerprint: str
    vad_identity_fingerprint: str
    frame_sequence: int
    pcm_sha256: str
    duration_ms: int
    sample_rate_hz: int
    previous_audio_chain_fingerprint: str
    fingerprint: str


@dataclass(frozen=True)
class VoiceSttInputProof:
    session_id: str
    language: str
    deployment_manifest_fingerprint: str
    wake_proof_fingerprint: str
    vad_identity_fingerprint: str
    stt_identity_fingerprint: str
    audio_chain_fingerprint: str
    audio_frame_count: int
    audio_duration_ms: int
    text_sha256: str
    fingerprint: str


class VoiceInputLineageTracker:
    """Hash-only microphone-to-STT lineage pinned to one deployment manifest.

    Raw audio and transcript text never enter this tracker. Audio frames form a rolling
    SHA-256 chain tied to the exact VAD deployment identity; the final STT proof then
    binds that chain to the exact wakeword/STT identities and deployment manifest.
    """

    def __init__(
        self,
        *,
        session_id: str,
        language: str,
        deployment_manifest_fingerprint: str,
        wakeword_identity_fingerprint: str,
        vad_identity_fingerprint: str,
        stt_identity_fingerprint: str,
    ) -> None:
        self.session_id = session_id.strip()
        self.language = language.strip().lower()
        self.deployment_manifest_fingerprint = deployment_manifest_fingerprint
        self.wakeword_identity_fingerprint = wakeword_identity_fingerprint
        self.vad_identity_fingerprint = vad_identity_fingerprint
        self.stt_identity_fingerprint = stt_identity_fingerprint
        if len(self.session_id) < 3:
            raise ValueError("voice_input_session_id_required")
        for value, code in (
            (deployment_manifest_fingerprint, "voice_input_deployment_manifest_invalid"),
            (wakeword_identity_fingerprint, "voice_input_wakeword_identity_invalid"),
            (vad_identity_fingerprint, "voice_input_vad_identity_invalid"),
            (stt_identity_fingerprint, "voice_input_stt_identity_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)
        self._wake: VoiceWakeInputProof | None = None
        self._audio_chain = self._empty_audio_chain()
        self._audio_frame_count = 0
        self._audio_duration_ms = 0

    def _empty_audio_chain(self) -> str:
        return _sha256(
            {
                "kind": "voice_audio_chain_start",
                "session_id": self.session_id,
                "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
                "vad_identity_fingerprint": self.vad_identity_fingerprint,
            }
        )

    def seal_wake(self) -> VoiceWakeInputProof:
        payload = {
            "session_id": self.session_id,
            "language": self.language,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "wakeword_identity_fingerprint": self.wakeword_identity_fingerprint,
        }
        self._wake = VoiceWakeInputProof(**payload, fingerprint=_sha256(payload))
        self._audio_chain = self._empty_audio_chain()
        self._audio_frame_count = 0
        self._audio_duration_ms = 0
        return self._wake

    def seal_audio_frame(self, frame: AudioFrame) -> VoiceAudioFrameProof:
        if self._wake is None:
            raise ValueError("voice_input_wake_proof_required")
        frame.validate()
        payload = {
            "session_id": self.session_id,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "vad_identity_fingerprint": self.vad_identity_fingerprint,
            "frame_sequence": frame.sequence,
            "pcm_sha256": frame.pcm_sha256,
            "duration_ms": frame.duration_ms,
            "sample_rate_hz": frame.sample_rate_hz,
            "previous_audio_chain_fingerprint": self._audio_chain,
        }
        proof = VoiceAudioFrameProof(**payload, fingerprint=_sha256(payload))
        self._audio_chain = proof.fingerprint
        self._audio_frame_count += 1
        self._audio_duration_ms += frame.duration_ms
        return proof

    def seal_stt_final(self, *, text_sha256: str) -> VoiceSttInputProof:
        if self._wake is None:
            raise ValueError("voice_input_wake_proof_required")
        if not _valid_sha256(text_sha256):
            raise ValueError("voice_input_stt_text_sha256_invalid")
        payload = {
            "session_id": self.session_id,
            "language": self.language,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "wake_proof_fingerprint": self._wake.fingerprint,
            "vad_identity_fingerprint": self.vad_identity_fingerprint,
            "stt_identity_fingerprint": self.stt_identity_fingerprint,
            "audio_chain_fingerprint": self._audio_chain,
            "audio_frame_count": self._audio_frame_count,
            "audio_duration_ms": self._audio_duration_ms,
            "text_sha256": text_sha256,
        }
        proof = VoiceSttInputProof(**payload, fingerprint=_sha256(payload))
        self._audio_chain = self._empty_audio_chain()
        self._audio_frame_count = 0
        self._audio_duration_ms = 0
        return proof
