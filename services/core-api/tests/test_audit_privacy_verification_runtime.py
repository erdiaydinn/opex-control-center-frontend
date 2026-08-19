import hashlib

from app.modules.audit.privacy_verification_runtime import (
    AuditPrivacyScanResult,
    AuditPrivacyVerificationRuntime,
)


class Scanner:
    def __init__(self, *, faces: int = 0, sensitive: int = 0, fail: bool = False):
        self.faces = faces
        self.sensitive = sensitive
        self.fail = fail

    def scan_jpeg(self, content: bytes) -> AuditPrivacyScanResult:
        if self.fail:
            raise RuntimeError("scanner unavailable")
        return AuditPrivacyScanResult(
            detected_face_count=self.faces,
            detected_sensitive_region_count=self.sensitive,
            scanner_model_ref="privacy-scanner:test",
            scanner_model_fingerprint="b" * 64,
        )


def expected(content: bytes) -> tuple[str, int]:
    return hashlib.sha256(content).hexdigest(), len(content)


def test_verified_requires_matching_bytes_and_zero_sensitive_regions() -> None:
    content = b"sanitized-jpeg"
    digest, size = expected(content)
    result = AuditPrivacyVerificationRuntime().verify_jpeg(
        content=content,
        expected_sha256=digest,
        expected_byte_size=size,
        scanner=Scanner(),
    )
    assert result.status == "verified"
    assert result.vision_inference_authorized is True


def test_hash_or_size_mismatch_is_tampered_and_never_authorized() -> None:
    content = b"sanitized-jpeg"
    result = AuditPrivacyVerificationRuntime().verify_jpeg(
        content=content,
        expected_sha256="a" * 64,
        expected_byte_size=len(content),
        scanner=Scanner(),
    )
    assert result.status == "tampered"
    assert result.vision_inference_authorized is False


def test_detected_face_rejects_sanitized_evidence() -> None:
    content = b"sanitized-jpeg"
    digest, size = expected(content)
    result = AuditPrivacyVerificationRuntime().verify_jpeg(
        content=content,
        expected_sha256=digest,
        expected_byte_size=size,
        scanner=Scanner(faces=1),
    )
    assert result.status == "rejected"
    assert result.vision_inference_authorized is False


def test_sensitive_region_rejects_evidence_even_without_face() -> None:
    content = b"sanitized-jpeg"
    digest, size = expected(content)
    result = AuditPrivacyVerificationRuntime().verify_jpeg(
        content=content,
        expected_sha256=digest,
        expected_byte_size=size,
        scanner=Scanner(sensitive=1),
    )
    assert result.status == "rejected"
    assert result.vision_inference_authorized is False


def test_scanner_failure_blocks_instead_of_guessing() -> None:
    content = b"sanitized-jpeg"
    digest, size = expected(content)
    result = AuditPrivacyVerificationRuntime().verify_jpeg(
        content=content,
        expected_sha256=digest,
        expected_byte_size=size,
        scanner=Scanner(fail=True),
    )
    assert result.status == "blocked"
    assert result.vision_inference_authorized is False


def test_missing_content_blocks() -> None:
    result = AuditPrivacyVerificationRuntime().verify_jpeg(
        content=b"",
        expected_sha256=hashlib.sha256(b"").hexdigest(),
        expected_byte_size=0,
        scanner=Scanner(),
    )
    assert result.status == "blocked"
    assert result.vision_inference_authorized is False
