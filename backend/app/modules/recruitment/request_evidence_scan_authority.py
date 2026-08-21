"""Transactional authority for signed request-level evidence scanner receipts."""
from __future__ import annotations

import base64
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from uuid import UUID, uuid4

from app.modules.workforce import persistence
from .scanner_database_authority import ScannerDatabaseAuthorityError, transaction as scanner_transaction
from .scanner_key_authority import AwsKmsHmacKeyAuthority, ScannerKeyAuthorityError
from .scanner_receipt import ReplayAuthority, ScannerReceipt, ScannerReceiptError, verify_scanner_receipt


class RequestEvidenceScanAuthorityError(ValueError):
    pass


def _verifier():
    try:
        return AwsKmsHmacKeyAuthority.from_environment().verify
    except ScannerKeyAuthorityError as error:
        raise RequestEvidenceScanAuthorityError(
            "Scanner KMS key authority hazır değil."
        ) from error


def record_verified_request_scan(
    request_id: str,
    payload: dict,
    signature: str,
    *,
    actor: str = "recruitment-scanner",
    now: datetime | None = None,
) -> dict:
    production = os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"
    required = 43 if production else 41
    if not persistence.ENABLED or (persistence.schema_version() or 0) < required:
        raise RequestEvidenceScanAuthorityError(
            f"PostgreSQL request scanner receipt otoritesi V{required} olmadan hazır değil."
        )
    try:
        evidence_id = UUID(str(payload.get("evidence_id", "")))
    except (TypeError, ValueError) as error:
        raise RequestEvidenceScanAuthorityError("Scanner receipt reddedildi.") from error
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    runtime_verifier = _verifier()

    try:
        with scanner_transaction() as (database, cursor):
            tenant_id = persistence.tenant_id()
            cursor.execute(
                """SELECT payload,revision
                   FROM recruitment_requests
                   WHERE tenant_id=%s AND id=%s
                   FOR UPDATE""",
                (tenant_id, request_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise RequestEvidenceScanAuthorityError("Scanner receipt reddedildi.")
            record, revision = row
            evidence = record.get("evidence") or {}
            if (
                evidence.get("id") != str(evidence_id)
                or evidence.get("storage_backend") != "S3_KMS_ENVELOPE"
                or not evidence.get("sha256")
            ):
                raise RequestEvidenceScanAuthorityError("Scanner receipt reddedildi.")
            if evidence.get("content_safety_state") == "MALWARE_DETECTED":
                raise RequestEvidenceScanAuthorityError("Scanner receipt reddedildi.")
            evidence_sha = str(evidence["sha256"])

            class DatabaseReplayAuthority(ReplayAuthority):
                def claim(self, claimed_tenant: str, provider: str, receipt_id: str) -> bool:
                    if claimed_tenant != tenant_id:
                        return False
                    try:
                        receipt = ScannerReceipt(**payload)
                        raw_signature = base64.urlsafe_b64decode(
                            signature + "=" * (-len(signature) % 4)
                        )
                        cursor.execute(
                            """SELECT recruitment.record_request_evidence_scan_receipt(
                                 %s,%s,%s,%s,%s,%s,%s,%s,%s,'HMAC-SHA256',%s,%s,%s
                               )""",
                            (
                                tenant_id,
                                uuid4(),
                                request_id,
                                evidence_id,
                                provider,
                                receipt.key_id,
                                receipt_id,
                                bytes.fromhex(receipt.evidence_sha256),
                                receipt.result,
                                sha256(receipt.canonical_bytes()).digest(),
                                sha256(raw_signature).digest(),
                                datetime.fromisoformat(receipt.issued_at.replace("Z", "+00:00")),
                            ),
                        )
                        return cursor.fetchone() is not None
                    except Exception:
                        return False

            try:
                receipt = verify_scanner_receipt(
                    payload,
                    signature,
                    verifier=runtime_verifier,
                    replay_authority=DatabaseReplayAuthority(),
                    expected_tenant_id=tenant_id,
                    expected_candidate_id=request_id,
                    expected_evidence_id=str(evidence_id),
                    expected_evidence_sha256=evidence_sha,
                    now=observed,
                )
            except (ScannerReceiptError, ValueError, TypeError) as error:
                database.rollback()
                raise RequestEvidenceScanAuthorityError("Scanner receipt reddedildi.") from error

            state = {
                "CLEAN": "MALWARE_CLEARED",
                "INFECTED": "MALWARE_DETECTED",
                "ERROR": "SCAN_FAILED",
            }[receipt.result]
            receipt_record = {
                "provider": receipt.provider,
                "engine": receipt.engine,
                "key_id": receipt.key_id,
                "receipt_id": receipt.receipt_id,
                "result": receipt.result,
                "evidence_sha256": receipt.evidence_sha256,
                "scanned_at": receipt.issued_at,
                "recorded_at": observed.isoformat(),
                "signature_verified": True,
            }
            evidence["content_safety_state"] = state
            evidence["content_safety_truth_boundary"] = "CRYPTOGRAPHIC_SCANNER_RECEIPT"
            evidence["content_safety_receipt"] = receipt_record
            evidence.setdefault("content_safety_receipts", []).append(receipt_record)
            record.setdefault("history", []).append(
                {
                    "at": observed.isoformat(),
                    "action": "REQUEST_EVIDENCE_CONTENT_SAFETY_SCANNED",
                    "actor": actor,
                    "evidence_id": str(evidence_id),
                    "evidence_sha256": evidence_sha,
                    "result": receipt.result,
                    "receipt_id": receipt.receipt_id,
                }
            )
            next_revision = int(revision) + 1
            record["revision"] = next_revision
            cursor.execute(
                """UPDATE recruitment_requests
                   SET revision=%s,payload=%s::jsonb
                   WHERE tenant_id=%s AND id=%s AND revision=%s""",
                (
                    next_revision,
                    json.dumps(record, ensure_ascii=False, default=str),
                    tenant_id,
                    request_id,
                    revision,
                ),
            )
            if cursor.rowcount != 1:
                database.rollback()
                raise RequestEvidenceScanAuthorityError("Scanner receipt reddedildi.")
            persistence._build_audit_record(
                cursor,
                "RECRUITMENT_REQUEST_EVIDENCE_CONTENT_SAFETY_SCANNED",
                actor,
                {
                    "record_id": request_id,
                    "evidence_id": str(evidence_id),
                    "evidence_sha256": evidence_sha,
                    "result": receipt.result,
                    "receipt_id": receipt.receipt_id,
                    "provider": receipt.provider,
                },
            )
            database.commit()
            return evidence
    except ScannerDatabaseAuthorityError as error:
        raise RequestEvidenceScanAuthorityError(str(error)) from error
