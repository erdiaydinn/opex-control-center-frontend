from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .voice_streaming import AudioFrame


T = TypeVar("T")


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class VoiceAudioBufferReceipt:
    session_id: str
    deployment_manifest_fingerprint: str
    frame: AudioFrame
    buffered_bytes: int
    buffered_frame_count: int
    fingerprint: str


@dataclass(frozen=True)
class EphemeralPcmFrameView:
    """Read-only view valid only during one data-plane processor callback."""

    sequence: int
    pcm: memoryview
    pcm_sha256: str
    duration_ms: int
    sample_rate_hz: int


@dataclass(frozen=True)
class VoiceAudioDataPlaneSnapshot:
    session_id: str
    deployment_manifest_fingerprint: str
    next_sequence: int
    buffered_bytes: int
    buffered_frame_count: int
    closed: bool
    fingerprint: str


@dataclass
class _OwnedFrame:
    metadata: AudioFrame
    pcm: bytearray


class VoiceAudioDataPlane(Generic[T]):
    """Bounded, RAM-only PCM ownership boundary for the local voice runtime.

    The control plane continues to receive hashes only. Raw PCM enters this object as
    an owned ``bytearray`` and is never serialized by the data plane. STT-style
    consumption is callback-only and wipes consumed buffers after the callback.
    VAD-style inspection can read the same buffers without consuming them so speech
    detection does not destroy audio that STT still needs. This is a best-effort
    application-memory wipe, not a claim that Python/OS/runtime copies outside this
    owner can be erased.
    """

    def __init__(
        self,
        *,
        session_id: str,
        deployment_manifest_fingerprint: str,
        max_buffer_bytes: int = 4 * 1024 * 1024,
        max_frames: int = 1000,
    ) -> None:
        self.session_id = session_id.strip()
        self.deployment_manifest_fingerprint = deployment_manifest_fingerprint
        self.max_buffer_bytes = int(max_buffer_bytes)
        self.max_frames = int(max_frames)
        if len(self.session_id) < 3:
            raise ValueError("voice_audio_dataplane_session_id_required")
        if not _valid_sha256(self.deployment_manifest_fingerprint):
            raise ValueError("voice_audio_dataplane_manifest_invalid")
        if not 64 * 1024 <= self.max_buffer_bytes <= 64 * 1024 * 1024:
            raise ValueError("voice_audio_dataplane_buffer_limit_invalid")
        if not 1 <= self.max_frames <= 10000:
            raise ValueError("voice_audio_dataplane_frame_limit_invalid")
        self._frames: list[_OwnedFrame] = []
        self._buffered_bytes = 0
        self._next_sequence = 0
        self._closed = False

    @staticmethod
    def _wipe(buffer: bytearray) -> None:
        buffer[:] = b"\x00" * len(buffer)

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("voice_audio_dataplane_closed")

    def _selected_views(self, max_frames: int) -> tuple[list[_OwnedFrame], tuple[EphemeralPcmFrameView, ...]]:
        self._require_open()
        if max_frames < 1:
            raise ValueError("voice_audio_dataplane_process_frame_count_invalid")
        if not self._frames:
            raise ValueError("voice_audio_dataplane_empty")
        count = min(int(max_frames), len(self._frames))
        selected = self._frames[:count]
        views = tuple(
            EphemeralPcmFrameView(
                sequence=item.metadata.sequence,
                pcm=memoryview(item.pcm).toreadonly(),
                pcm_sha256=item.metadata.pcm_sha256,
                duration_ms=item.metadata.duration_ms,
                sample_rate_hz=item.metadata.sample_rate_hz,
            )
            for item in selected
        )
        return selected, views

    @staticmethod
    def _release_views(views: tuple[EphemeralPcmFrameView, ...]) -> None:
        for view in views:
            try:
                view.pcm.release()
            except Exception:
                pass

    def push_owned_pcm(
        self,
        *,
        sequence: int,
        pcm: bytearray,
        duration_ms: int,
        sample_rate_hz: int,
        channels: int = 1,
        sample_width_bytes: int = 2,
    ) -> VoiceAudioBufferReceipt:
        """Transfer ownership of one PCM16-like mutable buffer into the data plane."""
        self._require_open()
        if not isinstance(pcm, bytearray):
            raise TypeError("voice_audio_dataplane_mutable_owned_buffer_required")
        if sequence != self._next_sequence:
            raise ValueError("voice_audio_dataplane_sequence_gap_or_replay")
        if channels != 1:
            raise ValueError("voice_audio_dataplane_mono_required")
        if sample_width_bytes != 2:
            raise ValueError("voice_audio_dataplane_pcm16_required")
        if not 1 <= int(duration_ms) <= 200:
            raise ValueError("voice_audio_dataplane_duration_invalid")
        if sample_rate_hz not in {16000, 24000, 48000}:
            raise ValueError("voice_audio_dataplane_sample_rate_unsupported")
        sample_product = int(sample_rate_hz) * int(duration_ms)
        if sample_product % 1000 != 0:
            raise ValueError("voice_audio_dataplane_fractional_sample_count")
        expected_bytes = (sample_product // 1000) * channels * sample_width_bytes
        if len(pcm) != expected_bytes:
            raise ValueError("voice_audio_dataplane_pcm_length_mismatch")
        if len(self._frames) + 1 > self.max_frames:
            raise ValueError("voice_audio_dataplane_frame_backpressure")
        if self._buffered_bytes + len(pcm) > self.max_buffer_bytes:
            raise ValueError("voice_audio_dataplane_byte_backpressure")

        digest = hashlib.sha256(pcm).hexdigest()
        frame = AudioFrame(
            sequence=sequence,
            pcm_sha256=digest,
            duration_ms=int(duration_ms),
            sample_rate_hz=int(sample_rate_hz),
        )
        frame.validate()
        self._frames.append(_OwnedFrame(metadata=frame, pcm=pcm))
        self._buffered_bytes += len(pcm)
        self._next_sequence += 1
        payload = {
            "session_id": self.session_id,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "sequence": frame.sequence,
            "pcm_sha256": frame.pcm_sha256,
            "duration_ms": frame.duration_ms,
            "sample_rate_hz": frame.sample_rate_hz,
            "buffered_bytes": self._buffered_bytes,
            "buffered_frame_count": len(self._frames),
        }
        return VoiceAudioBufferReceipt(
            session_id=self.session_id,
            deployment_manifest_fingerprint=self.deployment_manifest_fingerprint,
            frame=frame,
            buffered_bytes=self._buffered_bytes,
            buffered_frame_count=len(self._frames),
            fingerprint=_sha256(payload),
        )

    def inspect_next(self, *, max_frames: int, processor: Callable[[tuple[EphemeralPcmFrameView, ...]], T]) -> T:
        """Read buffered PCM in-memory without consuming it, intended for streaming VAD."""
        _, views = self._selected_views(max_frames)
        try:
            return processor(views)
        finally:
            self._release_views(views)

    def process_next(self, *, max_frames: int, processor: Callable[[tuple[EphemeralPcmFrameView, ...]], T]) -> T:
        """Process and one-shot consume up to ``max_frames`` without returning PCM."""
        selected, views = self._selected_views(max_frames)
        try:
            return processor(views)
        finally:
            self._release_views(views)
            consumed_bytes = 0
            for item in selected:
                consumed_bytes += len(item.pcm)
                self._wipe(item.pcm)
            del self._frames[: len(selected)]
            self._buffered_bytes -= consumed_bytes

    def discard_all(self) -> None:
        for item in self._frames:
            self._wipe(item.pcm)
        self._frames.clear()
        self._buffered_bytes = 0

    def close(self) -> None:
        if self._closed:
            return
        self.discard_all()
        self._closed = True

    def snapshot(self) -> VoiceAudioDataPlaneSnapshot:
        payload = {
            "session_id": self.session_id,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "next_sequence": self._next_sequence,
            "buffered_bytes": self._buffered_bytes,
            "buffered_frame_count": len(self._frames),
            "closed": self._closed,
        }
        return VoiceAudioDataPlaneSnapshot(**payload, fingerprint=_sha256(payload))

    def __enter__(self) -> "VoiceAudioDataPlane[T]":
        self._require_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
