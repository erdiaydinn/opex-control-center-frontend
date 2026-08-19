from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol

PrivacyVerificationStatus = Literal["verified", "rejected", "blocked", "tampered"]


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
        if len(self.scanner_model_fingerprint) != 64:
            raise ValueError("scanner_model_fingerprint must be SHA-256")


class AuditPrivacyEvidenceScanner(Protocol):
    def scan_jpeg(self, content: bytes) -> AuditPrivacyScanResult: ...


@dataclass(frozen=True)
class AuditServerPrivacyVerification:
    status: PrivacyVerificationStatus
    reason: str
    observed_sha256: str
    observed_byte_size: int
    scan: AuditPrivacyScanResult | None
    vision_inference_authorized: bool


class AuditPrivacyVerificationRuntime:
    """Verify sanitized evidence bytes before any vision inference authority exists.

    This runtime does not read storage and does not write verification events by itself. The
    internal worker must supply bytes from the private evidence store and persist the resulting
    receipt only after this function returns. Missing storage-read authority therefore cannot be
    misrepresented as a successful verification.
    """

    def verify_jpeg(
        self,
        *,
        content: bytes,
        expected_sha256: str,
        expected_byte_size: int,
        scanner: AuditPrivacyEvidenceScanner,
    ) -> AuditServerPrivacyVerification:
        if not content:
            return AuditServerPrivacyVerification(
                status="blocked",
                reason="private evidence content is unavailable",
                observed_sha256=hashlib.sha256(b"").hexdigest(),
                observed_byte_size=0,
                scan=None,
                vision_inference_authorized=False,
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
                vision_inference_authorized=False,
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
                vision_inference_authorized=False,
            )

        if scan.detected_face_count > 0 or scan.detected_sensitive_region_count > 0:
            return AuditServerPrivacyVerification(
                status="rejected",
                reason="sanitized evidence still contains privacy-sensitive regions",
                observed_sha256=observed_sha256,
                observed_byte_size=observed_byte_size,
                scan=scan,
                vision_inference_authorized=False,
            )

        return AuditServerPrivacyVerification(
            status="verified",
            reason="server hash/size and privacy scan passed",
            observed_sha256=observed_sha256,
            observed_byte_size=observed_byte_size,
            scan=scan,
            vision_inference_authorized=True,
        )
