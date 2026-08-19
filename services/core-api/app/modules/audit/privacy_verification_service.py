from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import text

from app.core.resources import engine
from app.modules.field_intelligence.evidence_object_read import read_private_evidence_object
from app.modules.field_intelligence.evidence_object_upload import FieldEvidenceStoreUnavailable
from app.modules.field_intelligence.repository import _set_tenant

from .privacy_verification_runtime import (
    AuditPrivacyEvidenceScanner,
    AuditPrivacyVerificationRuntime,
    AuditServerPrivacyVerification,
)
from .repository import AuditRepositoryError

PrivateEvidenceReader = Callable[..., Awaitable[bytes]]
SERVER_PRIVACY_VERIFIER_REF = "eay.audit.server_privacy.v1"
SERVER_PRIVACY_AUTHORITY_VERSION = "server_privacy_v2"


def _fingerprint(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    redaction_receipt_id: UUID,
    field_evidence_receipt_id: UUID,
    expected_sha256: str,
    expected_byte_size: int,
    result: AuditServerPrivacyVerification,
) -> str:
    scan = result.scan
    payload = {
        "audit_run_id": str(audit_run_id),
        "authority_version": SERVER_PRIVACY_AUTHORITY_VERSION,
        "detected_face_count": scan.detected_face_count if scan else None,
        "detected_sensitive_region_count": (
            scan.detected_sensitive_region_count if scan else None
        ),
        "expected_byte_size": expected_byte_size,
        "expected_sha256": expected_sha256,
        "field_evidence_receipt_id": str(field_evidence_receipt_id),
        "observed_byte_size": result.observed_byte_size,
        "observed_sha256": result.observed_sha256,
        "reason": result.reason,
        "redaction_receipt_id": str(redaction_receipt_id),
        "scanner_model_fingerprint": scan.scanner_model_fingerprint if scan else None,
        "scanner_model_ref": scan.scanner_model_ref if scan else None,
        "status": result.status,
        "tenant_id": tenant_id,
        "verifier_ref": SERVER_PRIVACY_VERIFIER_REF,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _load_bound_receipt(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    redaction_receipt_id: UUID,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT redaction.id AS redaction_receipt_id,
                       redaction.audit_run_id,
                       redaction.location_id,
                       redaction.field_evidence_receipt_id,
                       redaction.redacted_object_sha256,
                       redaction.redacted_object_byte_size,
                       field.receipt_id AS field_receipt_id,
                       field.mission_id,
                       field.location_id AS field_location_id,
                       field.media_type,
                       field.storage_provider,
                       field.sha256 AS field_sha256,
                       field.byte_size AS field_byte_size,
                       field.storage_receipt_hash,
                       field.expires_at,
                       run.field_mission_id,
                       run.location_id AS run_location_id,
                       run.status AS run_status
                FROM audit_redaction_receipts redaction
                JOIN audit_runs run
                  ON run.tenant_id=redaction.tenant_id
                 AND run.id=redaction.audit_run_id
                JOIN field_evidence_object_receipts field
                  ON field.tenant_id=redaction.tenant_id
                 AND field.receipt_id=redaction.field_evidence_receipt_id
                WHERE redaction.tenant_id=CAST(:tenant_id AS UUID)
                  AND redaction.audit_run_id=CAST(:audit_run_id AS UUID)
                  AND redaction.id=CAST(:redaction_receipt_id AS UUID)
                  AND field.expires_at > CURRENT_TIMESTAMP
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "redaction_receipt_id": str(redaction_receipt_id),
            },
        )
        row = result.mappings().first()
        if row is None:
            raise AuditRepositoryError("active server-bound Audit redaction receipt not found")
        bound = dict(row)

    if bound["run_status"] == "cancelled":
        raise AuditRepositoryError("cancelled audit run cannot verify privacy evidence")
    if bound["field_mission_id"] is None:
        raise AuditRepositoryError("audit run has no governed Field mission")
    if str(bound["mission_id"]) != str(bound["field_mission_id"]):
        raise AuditRepositoryError("private evidence mission no longer matches the audit run")
    if bound["field_location_id"] != bound["run_location_id"]:
        raise AuditRepositoryError("private evidence location no longer matches the audit run")
    if bound["location_id"] != bound["run_location_id"]:
        raise AuditRepositoryError("redaction receipt location no longer matches the audit run")
    if bound["storage_provider"] != "private_gateway":
        raise AuditRepositoryError("privacy verification requires the private Field gateway")
    if bound["media_type"] != "image/jpeg":
        raise AuditRepositoryError("server privacy verification currently supports image/jpeg only")
    if bound["redacted_object_sha256"] != bound["field_sha256"]:
        raise AuditRepositoryError("Audit binding hash no longer matches the Field receipt")
    if bound["redacted_object_byte_size"] != bound["field_byte_size"]:
        raise AuditRepositoryError("Audit binding byte size no longer matches the Field receipt")
    if not bound["storage_receipt_hash"] or len(str(bound["storage_receipt_hash"])) != 64:
        raise AuditRepositoryError("private gateway receipt integrity is unavailable")
    return bound


async def verify_bound_redaction_receipt(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    redaction_receipt_id: UUID,
    scanner: AuditPrivacyEvidenceScanner,
    reader: PrivateEvidenceReader = read_private_evidence_object,
) -> dict[str, object]:
    """Read, scan and append one server privacy verification event.

    A storage read failure is recorded as BLOCKED. VERIFIED means only that immutable sanitized
    bytes were server-read and passed the privacy scanner. It never grants vision-model execution.
    """

    bound = await _load_bound_receipt(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        redaction_receipt_id=redaction_receipt_id,
    )
    field_receipt_id = UUID(str(bound["field_receipt_id"]))
    expected_sha256 = str(bound["redacted_object_sha256"])
    expected_byte_size = int(bound["redacted_object_byte_size"])

    try:
        content = await reader(
            tenant_id=tenant_id,
            receipt_id=str(field_receipt_id),
            expected_byte_size=expected_byte_size,
        )
    except FieldEvidenceStoreUnavailable:
        content = b""

    verification = AuditPrivacyVerificationRuntime().verify_jpeg(
        content=content,
        expected_sha256=expected_sha256,
        expected_byte_size=expected_byte_size,
        scanner=scanner,
    )
    verification_fingerprint = _fingerprint(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        redaction_receipt_id=redaction_receipt_id,
        field_evidence_receipt_id=field_receipt_id,
        expected_sha256=expected_sha256,
        expected_byte_size=expected_byte_size,
        result=verification,
    )
    scan = verification.scan

    rebound = await _load_bound_receipt(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        redaction_receipt_id=redaction_receipt_id,
    )
    if (
        str(rebound["field_receipt_id"]) != str(field_receipt_id)
        or rebound["redacted_object_sha256"] != expected_sha256
        or int(rebound["redacted_object_byte_size"]) != expected_byte_size
    ):
        raise AuditRepositoryError("Audit privacy binding changed during verification")

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        inserted = await connection.execute(
            text(
                """
                INSERT INTO audit_redaction_verification_events (
                    tenant_id, redaction_receipt_id, verification_status,
                    verifier_ref, verification_authority_version,
                    verification_fingerprint, reason,
                    observed_sha256, observed_byte_size,
                    scanner_model_ref, scanner_model_fingerprint,
                    detected_face_count, detected_sensitive_region_count
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:redaction_receipt_id AS UUID),
                    :verification_status, :verifier_ref, :verification_authority_version,
                    :verification_fingerprint, :reason,
                    :observed_sha256, :observed_byte_size,
                    :scanner_model_ref, :scanner_model_fingerprint,
                    :detected_face_count, :detected_sensitive_region_count
                )
                RETURNING id, verified_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "redaction_receipt_id": str(redaction_receipt_id),
                "verification_status": verification.status,
                "verifier_ref": SERVER_PRIVACY_VERIFIER_REF,
                "verification_authority_version": SERVER_PRIVACY_AUTHORITY_VERSION,
                "verification_fingerprint": verification_fingerprint,
                "reason": verification.reason,
                "observed_sha256": verification.observed_sha256,
                "observed_byte_size": verification.observed_byte_size,
                "scanner_model_ref": scan.scanner_model_ref if scan else None,
                "scanner_model_fingerprint": (
                    scan.scanner_model_fingerprint if scan else None
                ),
                "detected_face_count": scan.detected_face_count if scan else None,
                "detected_sensitive_region_count": (
                    scan.detected_sensitive_region_count if scan else None
                ),
            },
        )
        row = inserted.mappings().one()

    return {
        "verification_event_id": str(row["id"]),
        "verified_at": row["verified_at"],
        "verification_status": verification.status,
        "verification_authority_version": SERVER_PRIVACY_AUTHORITY_VERSION,
        "verification_fingerprint": verification_fingerprint,
        "privacy_gate_passed": verification.privacy_gate_passed,
        "server_privacy_verified": verification.status == "verified",
        "vision_inference_authorized": False,
        "field_evidence_receipt_id": str(field_receipt_id),
        "redaction_receipt_id": str(redaction_receipt_id),
    }
