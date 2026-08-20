"""Seal deterministic scanner identity onto encrypted request evidence."""
from __future__ import annotations

import json
from uuid import NAMESPACE_URL, uuid5

from app.modules.workforce import persistence


class RequestEvidenceQuarantineError(ValueError):
    pass


def evidence_uuid(tenant_id: str, request_id: str, evidence_sha256: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"eay://recruitment/{tenant_id}/{request_id}/{evidence_sha256.lower()}",
        )
    )


def seal_request_evidence_quarantine(request_id: str, *, actor: str) -> dict:
    if not persistence.ENABLED or (persistence.schema_version() or 0) < 41:
        raise RequestEvidenceQuarantineError(
            "Request evidence scanner quarantine PostgreSQL V41 olmadan açılamaz."
        )
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
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
            raise RequestEvidenceQuarantineError("Talep bulunamadı.")
        record, revision = row
        evidence = record.get("evidence") or {}
        digest = str(evidence.get("sha256") or "").lower()
        if (
            evidence.get("storage_backend") != "S3_KMS_ENVELOPE"
            or len(digest) != 64
        ):
            raise RequestEvidenceQuarantineError(
                "Request evidence encrypted authority ile eşleşmiyor."
            )
        expected_id = evidence_uuid(tenant_id, request_id, digest)
        existing_id = evidence.get("id")
        if existing_id and existing_id != expected_id:
            raise RequestEvidenceQuarantineError(
                "Request evidence scanner identity bütünlük kontrolünü geçemedi."
            )
        if (
            existing_id == expected_id
            and evidence.get("content_safety_state")
            in {"STATIC_FORMAT_ACCEPTED_AV_PENDING", "MALWARE_CLEARED", "MALWARE_DETECTED", "SCAN_FAILED"}
        ):
            database.commit()
            return record

        evidence["id"] = expected_id
        evidence["content_safety_state"] = "STATIC_FORMAT_ACCEPTED_AV_PENDING"
        evidence["content_safety_truth_boundary"] = "NOT_MALWARE_CLEARED"
        evidence["content_safety_receipt"] = None
        record.setdefault("history", []).append(
            {
                "action": "REQUEST_EVIDENCE_QUARANTINED_FOR_SCANNER",
                "actor": actor,
                "evidence_id": expected_id,
                "evidence_sha256": digest,
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
            raise RequestEvidenceQuarantineError(
                "Request evidence quarantine eşzamanlı değişiklik nedeniyle reddedildi."
            )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_REQUEST_EVIDENCE_QUARANTINED",
            actor,
            {
                "record_id": request_id,
                "evidence_id": expected_id,
                "evidence_sha256": digest,
            },
        )
        database.commit()
        return record
