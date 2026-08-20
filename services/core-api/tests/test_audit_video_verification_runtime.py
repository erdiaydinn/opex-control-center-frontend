import hashlib

from app.modules.audit.privacy_verification_runtime import AuditPrivacyScanResult
from app.modules.audit.video_verification_runtime import (
    AuditDecodedVideo,
    AuditDecodedVideoFrame,
    AuditVideoVerificationRuntime,
)


def _frame(sequence: int, timestamp_ms: int) -> AuditDecodedVideoFrame:
    return AuditDecodedVideoFrame(
        sequence=sequence,
        timestamp_ms=timestamp_ms,
        jpeg_bytes=f"jpeg-{sequence}".encode(),
    )


class _Decoder:
    def __init__(self, decoded: AuditDecodedVideo) -> None:
        self.decoded = decoded
        self.calls = 0

    def decode_mp4(self, content: bytes) -> AuditDecodedVideo:
        self.calls += 1
        return self.decoded


class _FailingDecoder:
    def decode_mp4(self, content: bytes) -> AuditDecodedVideo:
        raise RuntimeError("decoder unavailable")


class _Scanner:
    def __init__(self, *, face_on_call: int | None = None) -> None:
        self.face_on_call = face_on_call
        self.calls = 0

    def scan_jpeg(self, content: bytes) -> AuditPrivacyScanResult:
        self.calls += 1
        return AuditPrivacyScanResult(
            detected_face_count=1 if self.calls == self.face_on_call else 0,
            detected_sensitive_region_count=0,
            scanner_model_ref="privacy-scanner-v1",
            scanner_model_fingerprint="a" * 64,
        )


def _decoded(*frames: AuditDecodedVideoFrame) -> AuditDecodedVideo:
    return AuditDecodedVideo(
        frames=tuple(frames),
        duration_ms=3_000,
        decoder_ref="canonical-video-decoder-v1",
        decoder_fingerprint="b" * 64,
    )


def _verify(content: bytes, decoder: object, scanner: object):
    return AuditVideoVerificationRuntime().verify_mp4(
        content=content,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_byte_size=len(content),
        decoder=decoder,
        scanner=scanner,
    )


def test_every_server_decoded_frame_must_pass_before_manifest_verifies() -> None:
    content = b"sanitized-private-mp4"
    decoder = _Decoder(_decoded(_frame(0, 0), _frame(1, 1000), _frame(2, 2000)))
    scanner = _Scanner()

    result = _verify(content, decoder, scanner)

    assert result.status == "verified"
    assert result.privacy_gate_passed is True
    assert result.vision_inference_authorized is False
    assert result.canonical_frame_count == 3
    assert result.processed_frame_count == 3
    assert len(result.frames) == 3
    assert scanner.calls == 3
    assert result.manifest_fingerprint is not None
    assert len(result.manifest_fingerprint) == 64


def test_face_remaining_in_any_frame_rejects_complete_video_authority() -> None:
    content = b"sanitized-private-mp4"
    decoder = _Decoder(_decoded(_frame(0, 0), _frame(1, 1000), _frame(2, 2000)))
    scanner = _Scanner(face_on_call=2)

    result = _verify(content, decoder, scanner)

    assert result.status == "rejected"
    assert result.privacy_gate_passed is False
    assert result.manifest_fingerprint is None
    assert result.processed_frame_count == 2
    assert len(result.frames) == 1
    assert scanner.calls == 2


def test_skipped_sequence_or_non_monotonic_time_fails_closed() -> None:
    content = b"sanitized-private-mp4"
    scanner = _Scanner()
    skipped = _Decoder(_decoded(_frame(0, 0), _frame(2, 1000)))
    skipped_result = _verify(content, skipped, scanner)
    assert skipped_result.status == "blocked"
    assert skipped_result.processed_frame_count == 1

    scanner = _Scanner()
    non_monotonic = _Decoder(_decoded(_frame(0, 1000), _frame(1, 1000)))
    time_result = _verify(content, non_monotonic, scanner)
    assert time_result.status == "blocked"
    assert time_result.processed_frame_count == 1


def test_source_tamper_is_rejected_before_decoder_or_scanner() -> None:
    content = b"changed-video"
    decoder = _Decoder(_decoded(_frame(0, 0)))
    scanner = _Scanner()
    result = AuditVideoVerificationRuntime().verify_mp4(
        content=content,
        expected_sha256="c" * 64,
        expected_byte_size=len(content),
        decoder=decoder,
        scanner=scanner,
    )

    assert result.status == "tampered"
    assert decoder.calls == 0
    assert scanner.calls == 0


def test_decoder_failure_blocks_without_fabricating_manifest() -> None:
    content = b"sanitized-private-mp4"
    scanner = _Scanner()
    result = _verify(content, _FailingDecoder(), scanner)

    assert result.status == "blocked"
    assert result.canonical_frame_count == 0
    assert result.manifest_fingerprint is None
    assert scanner.calls == 0
