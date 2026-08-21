from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal, Protocol

PrivacyVerificationStatus = Literal["verified", "rejected", "blocked", "tampered"]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AuditPrivacyScanResult:
    detected_face_count: int
    detected_sensitive_region_count: int
    scanner_model_ref: str
    scanner_model_fingerprint: str

    def __post_init__(self) -> None:
        if self.detected_face_count < 0 or self.detected_sensitive_region_count < 0:
            raise ValueError("privacy scan counts must be non-negative")
        if not self.scanner_model_ref.strip():
            raise ValueError("scanner_model_ref must not be blank")
        if not _SHA256_RE.fullmatch(self.scanner_model_fingerprint):
            raise ValueError("scanner_model_fingerprint must be lowercase SHA-256")


class AuditPrivacyEvidenceScanner(Protocol):
    def scan_jpeg(self, content: bytes) -> AuditPrivacyScanResult: ...


@dataclass(frozen=True)
class AuditServerPrivacyVerification:
    status: PrivacyVerificationStatus
    reason: str
    observed_sha256: str
    observed_byte_size: int
    scan: AuditPrivacyScanResult | None
    privacy_gate_passed: bool
    vision_inference_authorized: bool = False

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.observed_sha256):
            raise ValueError("observed_sha256 must be lowercase SHA-256")
        if self.observed_byte_size < 0:
            raise ValueError("observed_byte_size must be non-negative")
        if self.privacy_gate_passed != (self.status == "verified"):
            raise ValueError("privacy gate may pass only for a verified server privacy result")
        if self.vision_inference_authorized:
            raise ValueError(
                "privacy verification cannot grant downstream vision inference authority"
            )


class AuditPrivacyVerificationRuntime:
    """Verify sanitized evidence bytes without granting model execution authority.

    This runtime owns exactly one question: did the server read the immutable sanitized object and
    did an admitted privacy scanner find no privacy-sensitive regions? Even a VERIFIED result is
    only a privacy prerequisite. A separate governed vision-inference layer must still prove
    tenant scope, evidence-contract eligibility and model admission before any model is invoked.
    """

    def verify_jpeg(
        self,
        *,
        content: bytes,
        expected_sha256: str,
        expected_byte_size: int,
        scanner: AuditPrivacyEvidenceScanner,
    ) -> AuditServerPrivacyVerification:
        if not _SHA256_RE.fullmatch(expected_sha256):
            raise ValueError("expected_sha256 must be lowercase SHA-256")
        if expected_byte_size <= 0:
            return AuditServerPrivacyVerification(
                status="blocked",
                reason="immutable private evidence byte size is unavailable",
                observed_sha256=hashlib.sha256(content).hexdigest(),
                observed_byte_size=len(content),
                scan=None,
                privacy_gate_passed=False,
            )
        if not content:
            return AuditServerPrivacyVerification(
                status="blocked",
                reason="private evidence content is unavailable",
                observed_sha256=hashlib.sha256(b"").hexdigest(),
                observed_byte_size=0,
                scan=None,
                privacy_gate_passed=False,
            )

        observed_sha256 = hashlib.sha256(content).hexdigest()
        observed_byte_size = len(content)
        if observed_sha256 != expected_sha256 or observed_byte_size != expected_byte_size:
            return AuditServerPrivacyVerification(
                status="tampered",
                reason="private evidence bytes do not match the immutable storage receipt",
                observed_sha256=observed_sha256,
                observed_byte_size=observed_byte_size,
                scan=None,
                privacy_gate_passed=False,
            )

        try:
            scan = scanner.scan_jpeg(content)
        except Exception:
            return AuditServerPrivacyVerification(
                status="blocked",
                reason="server privacy scanner failed closed",
                observed_sha256=observed_sha256,
                observed_byte_size=observed_byte_size,
                scan=None,
                privacy_gate_passed=False,
            )

        if scan.detected_face_count > 0 or scan.detected_sensitive_region_count > 0:
            return AuditServerPrivacyVerification(
                status="rejected",
                reason="sanitized evidence still contains privacy-sensitive regions",
                observed_sha256=observed_sha256,
                observed_byte_size=observed_byte_size,
                scan=scan,
                privacy_gate_passed=False,
            )

        return AuditServerPrivacyVerification(
            status="verified",
            reason="server hash/size and privacy scan passed",
            observed_sha256=observed_sha256,
            observed_byte_size=observed_byte_size,
            scan=scan,
            privacy_gate_passed=True,
        )
