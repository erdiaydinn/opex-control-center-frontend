"""Transactional PostgreSQL authority for cryptographically verified scanner receipts."""
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
from .scanner_receipt import ReplayAuthority, ScannerReceipt, SignatureVerifier, verify_scanner_receipt


class CandidateScanAuthorityError(ValueError):
    pass


def _select_verifier(verifier: SignatureVerifier | None) -> SignatureVerifier:
    if os.getenv("DOCKOS_ENV", "development").strip().lower() == "production":
        try:
            return AwsKmsHmacKeyAuthority.from_environment().verify
        except ScannerKeyAuthorityError as error:
            raise CandidateScanAuthorityError(
                "Production scanner KMS key authority hazır değil."
            ) from error
    if verifier is not None:
        return verifier
    try:
        return AwsKmsHmacKeyAuthority.from_environment().verify
    except ScannerKeyAuthorityError as error:
        raise CandidateScanAuthorityError("Scanner key authority hazır değil.") from error


def record_verified_scan(
    payload: dict,
    signature: str,
    *,
    verifier: SignatureVerifier | None = None,
    actor: str,
    now: datetime | None = None,
) -> dict:
    production = os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"
    required_schema = 43 if production else 39
    if not persistence.ENABLED or (persistence.schema_version() or 0) < required_schema:
        raise CandidateScanAuthorityError("PostgreSQL scanner receipt otoritesi hazır değil.")

    runtime_verifier = _select_verifier(verifier)
    try:
        evidence_id = UUID(str(payload.get("evidence_id", "")))
    except (TypeError, ValueError) as error:
        raise CandidateScanAuthorityError("Scanner receipt reddedildi.") from error

    observed = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        scanner_context = scanner_transaction()
        with scanner_context as (database, cursor):
            tenant_id = persistence.tenant_id()
            cursor.execute(
                "SELECT * FROM recruitment.get_candidate_evidence_scan_binding(%s,%s)",
                (tenant_id, evidence_id),
            )
            binding = cursor.fetchone()
            if binding is None:
                raise CandidateScanAuthorityError("Scanner receipt reddedildi.")
            request_id, candidate_id, evidence_digest = binding
            evidence_hex = bytes(evidence_digest).hex()

            class DatabaseReplayAuthority(ReplayAuthority):
                def claim(self, claimed_tenant: str, provider: str, receipt_id: str) -> bool:
                    if claimed_tenant != tenant_id:
                        return False
                    try:
                        raw_signature = base64.urlsafe_b64decode(
                            signature + "=" * (-len(signature) % 4)
                        )
                        receipt = ScannerReceipt(**payload)
                        cursor.execute(
                            """SELECT recruitment.record_candidate_evidence_scan_receipt(
                                 %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                               )""",
                            (
                                tenant_id,
                                uuid4(),
                                evidence_id,
                                provider,
                                receipt.key_id,
                                receipt_id,
                                bytes.fromhex(receipt.evidence_sha256),
                                receipt.result,
                                "HMAC-SHA256",
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
                    expected_candidate_id=str(candidate_id),
                    expected_evidence_id=str(evidence_id),
                    expected_evidence_sha256=evidence_hex,
                    now=observed,
                )
            except Exception as error:
                database.rollback()
                raise CandidateScanAuthorityError("Scanner receipt reddedildi.") from error

            cursor.execute(
                """SELECT payload,revision
                   FROM recruitment_requests
                   WHERE tenant_id=%s AND id=%s
                   FOR UPDATE""",
                (tenant_id, request_id),
            )
            aggregate = cursor.fetchone()
            if aggregate is None:
                database.rollback()
                raise CandidateScanAuthorityError("Scanner receipt reddedildi.")
            record, revision = aggregate
            candidate = next(
                (item for item in record.get("candidates", []) if item.get("id") == candidate_id),
                None,
            )
            evidence = next(
                (
                    item
                    for item in (candidate or {}).get("evidence", [])
                    if item.get("id") == str(evidence_id)
                    and item.get("sha256") == evidence_hex
                ),
                None,
            )
            if evidence is None or evidence.get("content_safety_state") == "MALWARE_DETECTED":
                database.rollback()
                raise CandidateScanAuthorityError("Scanner receipt reddedildi.")

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
                    "action": "CANDIDATE_EVIDENCE_CONTENT_SAFETY_SCANNED",
                    "actor": actor,
                    "candidate_id": candidate_id,
                    "evidence_sha256": evidence_hex,
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
                raise CandidateScanAuthorityError("Scanner receipt reddedildi.")
            persistence._build_audit_record(
                cursor,
                "RECRUITMENT_CANDIDATE_EVIDENCE_CONTENT_SAFETY_SCANNED",
                actor,
                {
                    "record_id": request_id,
                    "candidate_id": candidate_id,
                    "evidence_sha256": evidence_hex,
                    "result": receipt.result,
                    "receipt_id": receipt.receipt_id,
                    "provider": receipt.provider,
                },
            )
            database.commit()
            return evidence
    except ScannerDatabaseAuthorityError as error:
        raise CandidateScanAuthorityError(str(error)) from error
