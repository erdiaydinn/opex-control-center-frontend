"""PostgreSQL authority for one-time candidate document uploads.

The bearer secret is resolved and consumed in the same transaction that creates
the immutable evidence authority and updates the recruitment aggregate.  File
bytes are staged and validated before that transaction, so malformed uploads do
not burn a capability.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import tempfile
from uuid import uuid4

from app.modules.workforce import persistence


class CandidateUploadAuthorityError(ValueError):
    pass


def _invalid() -> CandidateUploadAuthorityError:
    # Deliberately identical for unknown, expired, revoked, and cross-tenant tokens.
    return CandidateUploadAuthorityError("Aday yükleme yetkisi geçersiz veya süresi dolmuş.")


def _token_digest(raw_token: str) -> bytes:
    token = str(raw_token or "").strip()
    if not 32 <= len(token) <= 256:
        raise _invalid()
    return sha256(token.encode("utf-8")).digest()


def issue(
    request_id: str,
    candidate_id: str,
    document_type: str,
    expires_in_minutes: int,
    actor: str,
) -> dict:
    if not persistence.ENABLED:
        raise CandidateUploadAuthorityError("PostgreSQL aday yükleme otoritesi yapılandırılmadı.")
    raw_token = secrets.token_urlsafe(32)
    digest = _token_digest(raw_token)
    capability_id = uuid4()
    staging_key = f"quarantine/{persistence.tenant_id()}/{capability_id}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=expires_in_minutes)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        tenant_id = persistence.tenant_id()
        cursor.execute(
            "SELECT payload, revision FROM recruitment_requests "
            "WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (tenant_id, request_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise CandidateUploadAuthorityError("Aday bulunamadı veya belge kabul eden aşamada değil.")
        record, revision = row
        candidate = next((item for item in record.get("candidates", []) if item.get("id") == candidate_id), None)
        if candidate is None or candidate.get("status") not in {"EVIDENCE_PENDING", "REVIEW_PENDING"}:
            raise CandidateUploadAuthorityError("Aday bulunamadı veya belge kabul eden aşamada değil.")
        cursor.execute(
            """SELECT * FROM recruitment.issue_candidate_upload_capability(
                 %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
               )""",
            (tenant_id, capability_id, request_id, candidate_id, digest, document_type,
             staging_key, 10 * 1024 * 1024, expires_at, actor),
        )
        issued = cursor.fetchone()
        if issued is None:
            raise CandidateUploadAuthorityError("Aday yükleme yetkisi oluşturulamadı.")
        record.setdefault("history", []).append({
            "at": now.isoformat(), "action": "CANDIDATE_UPLOAD_CAPABILITY_ISSUED",
            "actor": actor, "candidate_id": candidate_id,
            "capability_id": str(capability_id), "document_type": document_type,
        })
        next_revision = int(revision) + 1
        record["revision"] = next_revision
        cursor.execute(
            "UPDATE recruitment_requests SET revision=%s,payload=%s::jsonb "
            "WHERE tenant_id=%s AND id=%s AND revision=%s",
            (next_revision, json.dumps(record, ensure_ascii=False, default=str),
             tenant_id, request_id, revision),
        )
        persistence._build_audit_record(cursor, "RECRUITMENT_CANDIDATE_UPLOAD_CAPABILITY_ISSUED", actor, {
            "record_id": request_id, "candidate_id": candidate_id,
            "capability_id": str(capability_id), "document_type": document_type,
        })
        database.commit()
    return {
        "capability": raw_token, "expires_at": expires_at.isoformat(),
        "document_type": document_type, "max_uploads": 1,
    }


def finalize(
    raw_token: str,
    document_type: str,
    filename: str,
    content_type: str,
    content: bytes,
    evidence_dir: Path,
    *,
    retention_days: int,
) -> dict:
    """Stage bytes, then atomically consume authority and persist exact evidence."""
    if not persistence.ENABLED:
        raise CandidateUploadAuthorityError("PostgreSQL aday yükleme otoritesi yapılandırılmadı.")
    digest = _token_digest(raw_token)
    evidence_digest = sha256(content).digest()
    evidence_id = uuid4()
    suffix = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[content_type]
    evidence_dir.mkdir(parents=True, exist_ok=True)
    staged_path: Path | None = None
    authoritative_path: Path | None = None
    commit_started = False
    try:
        descriptor, staged_name = tempfile.mkstemp(
            dir=evidence_dir, prefix=".candidate-quarantine-", suffix=suffix,
        )
        staged_path = Path(staged_name)
        with os.fdopen(descriptor, "wb") as staged_file:
            staged_file.write(content)
            staged_file.flush()
            os.fsync(staged_file.fileno())
        with persistence.connection() as database, database.cursor() as cursor:
            persistence._set_tenant(cursor)
            tenant_id = persistence.tenant_id()
            now = datetime.now(UTC)
            retention_until = now + timedelta(days=retention_days)
            cursor.execute(
                """SELECT * FROM recruitment.finalize_candidate_evidence_upload(
                     %s,%s,%s,%s,%s,%s,%s,%s,%s
                   )""",
                (tenant_id, digest, document_type, evidence_id, Path(filename).name[:240],
                 content_type, len(content), evidence_digest, retention_until),
            )
            authority = cursor.fetchone()
            if authority is None:
                raise _invalid()
            (returned_evidence_id, capability_id, request_id, candidate_id,
             bound_type, object_key) = authority
            if returned_evidence_id != evidence_id:
                raise CandidateUploadAuthorityError("Aday kanıt otoritesi bütünlük kontrolünü geçemedi.")
            relative_object = Path(str(object_key))
            expected_prefix = ("quarantine", tenant_id)
            if (
                relative_object.is_absolute()
                or ".." in relative_object.parts
                or relative_object.parts[:2] != expected_prefix
                or len(relative_object.parts) != 3
            ):
                raise CandidateUploadAuthorityError("Aday kanıt nesne otoritesi geçersiz.")
            authoritative_path = evidence_dir / relative_object
            authoritative_path.parent.mkdir(parents=True, exist_ok=True)
            with authoritative_path.open("xb") as authority_file:
                authority_file.write(content)
                authority_file.flush()
                os.fsync(authority_file.fileno())

            # The SECURITY DEFINER function consumed the authority, but it is
            # still inside this transaction. Any aggregate/audit failure below
            # rolls the evidence and consumption back together.
            cursor.execute(
                "SELECT payload,revision FROM recruitment_requests "
                "WHERE tenant_id=%s AND id=%s FOR UPDATE",
                (tenant_id, request_id),
            )
            aggregate_row = cursor.fetchone()
            if aggregate_row is None:
                raise _invalid()
            record, revision = aggregate_row
            candidate = next((item for item in record.get("candidates", []) if item.get("id") == candidate_id), None)
            if candidate is None or candidate.get("status") not in {"EVIDENCE_PENDING", "REVIEW_PENDING"}:
                raise _invalid()
            evidence = {
                "id": str(evidence_id), "original_name": Path(filename).name[:240],
                "content_type": content_type, "size": len(content),
                "sha256": evidence_digest.hex(), "stored_name": str(relative_object),
                "uploaded_at": now.isoformat(),
                "uploaded_by": f"candidate-capability:{capability_id}",
                "retention_until": retention_until.isoformat(), "document_type": bound_type,
                "requires_official_verification": bound_type != "OTHER",
                "verification_state": "BARCODE_EXTRACTION_PENDING" if bound_type != "OTHER" else "NOT_REQUIRED",
                "official_verification": None,
                "content_safety_state": "STATIC_FORMAT_ACCEPTED_AV_PENDING",
                "content_safety_truth_boundary": "NOT_MALWARE_CLEARED",
            }
            candidate.setdefault("evidence", []).append(evidence)
            candidate["status"] = "REVIEW_PENDING"
            record.setdefault("history", []).append({
                "at": now.isoformat(), "action": "CANDIDATE_EVIDENCE_UPLOADED",
                "actor": evidence["uploaded_by"], "candidate_id": candidate_id,
                "sha256": evidence_digest.hex(), "capability_id": str(capability_id),
            })
            next_revision = int(revision) + 1
            record["revision"] = next_revision
            cursor.execute(
                "UPDATE recruitment_requests SET status=%s,revision=%s,payload=%s::jsonb "
                "WHERE tenant_id=%s AND id=%s AND revision=%s",
                (record["status"], next_revision, json.dumps(record, ensure_ascii=False, default=str),
                 tenant_id, request_id, revision),
            )
            if cursor.rowcount != 1:
                raise CandidateUploadAuthorityError("İşe alım kaydı eşzamanlı olarak değiştirildi.")
            persistence._build_audit_record(cursor, "RECRUITMENT_CANDIDATE_EVIDENCE_UPLOADED", evidence["uploaded_by"], {
                "record_id": request_id, "candidate_id": candidate_id,
                "capability_id": str(capability_id), "evidence_id": str(evidence_id),
                "sha256": evidence_digest.hex(), "size": len(content),
            })
            staged_path.unlink(missing_ok=True)
            commit_started = True
            database.commit()
            return evidence
    except Exception:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        if authoritative_path is not None and not commit_started:
            authoritative_path.unlink(missing_ok=True)
        raise
