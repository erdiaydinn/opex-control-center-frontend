from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from .privacy_verification_runtime import (
    AuditPrivacyEvidenceScanner,
    AuditPrivacyVerificationRuntime,
)

VideoVerificationStatus = Literal["verified", "rejected", "blocked", "tampered"]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_CANONICAL_VIDEO_FRAMES = 1_800
MAX_CANONICAL_FRAME_BYTES = 8 * 1024 * 1024
MAX_VIDEO_DURATION_MS = 30 * 60 * 1000


@dataclass(frozen=True)
class AuditDecodedVideoFrame:
    sequence: int
    timestamp_ms: int
    jpeg_bytes: bytes


@dataclass(frozen=True)
class AuditDecodedVideo:
    frames: tuple[AuditDecodedVideoFrame, ...]
    duration_ms: int
    decoder_ref: str
    decoder_fingerprint: str

    def __post_init__(self) -> None:
        if not self.decoder_ref.strip():
            raise ValueError("decoder_ref must not be blank")
        if not _SHA256_RE.fullmatch(self.decoder_fingerprint):
            raise ValueError("decoder_fingerprint must be lowercase SHA-256")


class AuditPrivateVideoDecoder(Protocol):
    def decode_mp4(self, content: bytes) -> AuditDecodedVideo: ...


@dataclass(frozen=True)
class AuditCanonicalVideoFrame:
    sequence: int
    timestamp_ms: int
    sha256: str
    byte_size: int
    privacy_verification_fingerprint: str


@dataclass(frozen=True)
class AuditCanonicalVideoManifest:
    status: VideoVerificationStatus
    reason: str
    source_sha256: str
    source_byte_size: int
    duration_ms: int | None
    canonical_frame_count: int
    processed_frame_count: int
    decoder_ref: str | None
    decoder_fingerprint: str | None
    frames: tuple[AuditCanonicalVideoFrame, ...]
    manifest_fingerprint: str | None
    privacy_gate_passed: bool
    vision_inference_authorized: bool = False

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be lowercase SHA-256")
        if self.source_byte_size < 0:
            raise ValueError("source_byte_size must be non-negative")
        if self.canonical_frame_count < 0 or self.processed_frame_count < 0:
            raise ValueError("frame counts must be non-negative")
        if self.processed_frame_count > self.canonical_frame_count:
            raise ValueError("processed frame count cannot exceed canonical frame count")
        if self.privacy_gate_passed != (self.status == "verified"):
            raise ValueError("video privacy gate may pass only for a verified manifest")
        if self.vision_inference_authorized:
            raise ValueError("video verification cannot grant vision inference authority")
        if self.status == "verified":
            if self.canonical_frame_count <= 0:
                raise ValueError("verified video manifest must contain canonical frames")
            if self.processed_frame_count != self.canonical_frame_count:
                raise ValueError("verified video manifest requires complete canonical coverage")
            if len(self.frames) != self.canonical_frame_count:
                raise ValueError("verified video manifest frame list is incomplete")
            if not self.manifest_fingerprint or not _SHA256_RE.fullmatch(
                self.manifest_fingerprint
            ):
                raise ValueError("verified video manifest requires a SHA-256 fingerprint")


def _frame_verification_fingerprint(
    *,
    source_sha256: str,
    sequence: int,
    timestamp_ms: int,
    frame_sha256: str,
    scanner_model_ref: str,
    scanner_model_fingerprint: str,
) -> str:
    payload = {
        "frame_sha256": frame_sha256,
        "scanner_model_fingerprint": scanner_model_fingerprint,
        "scanner_model_ref": scanner_model_ref,
        "sequence": sequence,
        "source_sha256": source_sha256,
        "timestamp_ms": timestamp_ms,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _manifest_fingerprint(
    *,
    source_sha256: str,
    source_byte_size: int,
    decoded: AuditDecodedVideo,
    frames: tuple[AuditCanonicalVideoFrame, ...],
) -> str:
    payload = {
        "decoder_fingerprint": decoded.decoder_fingerprint,
        "decoder_ref": decoded.decoder_ref,
        "duration_ms": decoded.duration_ms,
        "frames": [
            {
                "byte_size": frame.byte_size,
                "privacy_verification_fingerprint": frame.privacy_verification_fingerprint,
                "sequence": frame.sequence,
                "sha256": frame.sha256,
                "timestamp_ms": frame.timestamp_ms,
            }
            for frame in frames
        ],
        "source_byte_size": source_byte_size,
        "source_sha256": source_sha256,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditVideoVerificationRuntime:
    """Verify sanitized private video bytes and derive a canonical privacy-safe frame manifest.

    The runtime never treats a client frame list as canonical. Frames come only from a server-owned
    decoder operating on immutable sanitized video bytes. Every canonical frame must pass the
    server privacy scanner before a manifest can be VERIFIED. A verified manifest is still only a
    privacy/evidence prerequisite; it cannot authorize a vision model or create a finding.
    """

    def verify_mp4(
        self,
        *,
        content: bytes,
        expected_sha256: str,
        expected_byte_size: int,
        decoder: AuditPrivateVideoDecoder,
        scanner: AuditPrivacyEvidenceScanner,
    ) -> AuditCanonicalVideoManifest:
        if not _SHA256_RE.fullmatch(expected_sha256):
            raise ValueError("expected_sha256 must be lowercase SHA-256")

        observed_sha256 = hashlib.sha256(content).hexdigest()
        observed_byte_size = len(content)
        if expected_byte_size <= 0 or not content:
            return AuditCanonicalVideoManifest(
                status="blocked",
                reason="private sanitized video bytes are unavailable",
                source_sha256=observed_sha256,
                source_byte_size=observed_byte_size,
                duration_ms=None,
                canonical_frame_count=0,
                processed_frame_count=0,
                decoder_ref=None,
                decoder_fingerprint=None,
                frames=(),
                manifest_fingerprint=None,
                privacy_gate_passed=False,
            )
        if observed_sha256 != expected_sha256 or observed_byte_size != expected_byte_size:
            return AuditCanonicalVideoManifest(
                status="tampered",
                reason="private video bytes do not match the immutable storage receipt",
                source_sha256=observed_sha256,
                source_byte_size=observed_byte_size,
                duration_ms=None,
                canonical_frame_count=0,
                processed_frame_count=0,
                decoder_ref=None,
                decoder_fingerprint=None,
                frames=(),
                manifest_fingerprint=None,
                privacy_gate_passed=False,
            )

        try:
            decoded = decoder.decode_mp4(content)
        except Exception:
            return AuditCanonicalVideoManifest(
                status="blocked",
                reason="server video decoder failed closed",
                source_sha256=observed_sha256,
                source_byte_size=observed_byte_size,
                duration_ms=None,
                canonical_frame_count=0,
                processed_frame_count=0,
                decoder_ref=None,
                decoder_fingerprint=None,
                frames=(),
                manifest_fingerprint=None,
                privacy_gate_passed=False,
            )

        frame_count = len(decoded.frames)
        if (
            decoded.duration_ms <= 0
            or decoded.duration_ms > MAX_VIDEO_DURATION_MS
            or frame_count <= 0
            or frame_count > MAX_CANONICAL_VIDEO_FRAMES
        ):
            return self._blocked_manifest(
                source_sha256=observed_sha256,
                source_byte_size=observed_byte_size,
                decoded=decoded,
                reason="decoded video duration/frame count is outside the governed limits",
            )

        previous_timestamp = -1
        verified_frames: list[AuditCanonicalVideoFrame] = []
        for expected_sequence, frame in enumerate(decoded.frames):
            if (
                frame.sequence != expected_sequence
                or frame.timestamp_ms <= previous_timestamp
                or frame.timestamp_ms < 0
                or frame.timestamp_ms > decoded.duration_ms
                or not frame.jpeg_bytes
                or len(frame.jpeg_bytes) > MAX_CANONICAL_FRAME_BYTES
            ):
                return self._blocked_manifest(
                    source_sha256=observed_sha256,
                    source_byte_size=observed_byte_size,
                    decoded=decoded,
                    reason="canonical frame sequence/timestamp/content validation failed",
                    processed_frame_count=len(verified_frames),
                    frames=tuple(verified_frames),
                )

            frame_sha256 = hashlib.sha256(frame.jpeg_bytes).hexdigest()
            privacy = AuditPrivacyVerificationRuntime().verify_jpeg(
                content=frame.jpeg_bytes,
                expected_sha256=frame_sha256,
                expected_byte_size=len(frame.jpeg_bytes),
                scanner=scanner,
            )
            if privacy.status != "verified" or privacy.scan is None:
                return AuditCanonicalVideoManifest(
                    status=privacy.status,
                    reason=f"canonical frame {frame.sequence} failed server privacy verification",
                    source_sha256=observed_sha256,
                    source_byte_size=observed_byte_size,
                    duration_ms=decoded.duration_ms,
                    canonical_frame_count=frame_count,
                    processed_frame_count=len(verified_frames) + 1,
                    decoder_ref=decoded.decoder_ref,
                    decoder_fingerprint=decoded.decoder_fingerprint,
                    frames=tuple(verified_frames),
                    manifest_fingerprint=None,
                    privacy_gate_passed=False,
                )

            verified_frames.append(
                AuditCanonicalVideoFrame(
                    sequence=frame.sequence,
                    timestamp_ms=frame.timestamp_ms,
                    sha256=frame_sha256,
                    byte_size=len(frame.jpeg_bytes),
                    privacy_verification_fingerprint=_frame_verification_fingerprint(
                        source_sha256=observed_sha256,
                        sequence=frame.sequence,
                        timestamp_ms=frame.timestamp_ms,
                        frame_sha256=frame_sha256,
                        scanner_model_ref=privacy.scan.scanner_model_ref,
                        scanner_model_fingerprint=privacy.scan.scanner_model_fingerprint,
                    ),
                )
            )
            previous_timestamp = frame.timestamp_ms

        frames = tuple(verified_frames)
        return AuditCanonicalVideoManifest(
            status="verified",
            reason="all server-decoded canonical frames passed privacy verification",
            source_sha256=observed_sha256,
            source_byte_size=observed_byte_size,
            duration_ms=decoded.duration_ms,
            canonical_frame_count=frame_count,
            processed_frame_count=frame_count,
            decoder_ref=decoded.decoder_ref,
            decoder_fingerprint=decoded.decoder_fingerprint,
            frames=frames,
            manifest_fingerprint=_manifest_fingerprint(
                source_sha256=observed_sha256,
                source_byte_size=observed_byte_size,
                decoded=decoded,
                frames=frames,
            ),
            privacy_gate_passed=True,
        )

    @staticmethod
    def _blocked_manifest(
        *,
        source_sha256: str,
        source_byte_size: int,
        decoded: AuditDecodedVideo,
        reason: str,
        processed_frame_count: int = 0,
        frames: tuple[AuditCanonicalVideoFrame, ...] = (),
    ) -> AuditCanonicalVideoManifest:
        return AuditCanonicalVideoManifest(
            status="blocked",
            reason=reason,
            source_sha256=source_sha256,
            source_byte_size=source_byte_size,
            duration_ms=decoded.duration_ms,
            canonical_frame_count=len(decoded.frames),
            processed_frame_count=processed_frame_count,
            decoder_ref=decoded.decoder_ref,
            decoder_fingerprint=decoded.decoder_fingerprint,
            frames=frames,
            manifest_fingerprint=None,
            privacy_gate_passed=False,
        )
