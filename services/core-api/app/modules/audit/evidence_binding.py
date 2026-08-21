from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from app.core.resources import engine
from app.modules.field_intelligence.repository import _set_tenant

from .repository import AuditConflictError, AuditRepositoryError

AUDIT_BINDABLE_MEDIA: dict[str, tuple[str, int, int]] = {
    "image/jpeg": ("image", 1, 1),
    "video/mp4": ("video", 0, 0),
}


def _dict(row) -> dict[str, object]:
    return dict(row._mapping)


async def bind_server_evidence_to_redaction_receipt(
    tenant_id: str,
    audit_run_id: UUID,
    *,
    field_evidence_receipt_id: UUID,
    source_fingerprint: str,
    privacy_policy_version: str,
    detector_model_ref: str,
    device_id: str | None,
) -> dict[str, object]:
    """Bind client provenance to one server-issued private evidence receipt.

    Media kind and coverage state are derived from the immutable Field receipt, never from the
    client. JPEG is already a single canonical image. MP4 begins with zero canonical frames;
    frame truth exists only after the server-owned video decoder and privacy scanner run.
    Neither binding grants server privacy verification or downstream model authority.
    """

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        run_result = await connection.execute(
            text(
                """
                SELECT id, field_mission_id, location_id, status
                FROM audit_runs
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:audit_run_id AS UUID)
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "audit_run_id": str(audit_run_id)},
        )
        run = run_result.first()
        if not run or run.status == "cancelled":
            raise AuditRepositoryError("audit run not found or cancelled")
        if run.field_mission_id is None:
            raise AuditRepositoryError(
                "audit run has no governed Field mission for evidence binding"
            )

        field_result = await connection.execute(
            text(
                """
                SELECT receipt_id, mission_id, location_id, field_key, media_type,
                       sha256, byte_size, storage_provider, storage_receipt_hash,
                       client_submission_id, received_at, expires_at
                FROM field_evidence_object_receipts
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND receipt_id = CAST(:field_evidence_receipt_id AS UUID)
                  AND mission_id = CAST(:mission_id AS UUID)
                  AND location_id = :location_id
                  AND expires_at > CURRENT_TIMESTAMP
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "field_evidence_receipt_id": str(field_evidence_receipt_id),
                "mission_id": str(run.field_mission_id),
                "location_id": run.location_id,
            },
        )
        field_receipt = field_result.first()
        if not field_receipt:
            raise AuditRepositoryError(
                "active private evidence receipt does not belong to this audit run mission/location"
            )
        if field_receipt.storage_provider != "private_gateway":
            raise AuditRepositoryError("Audit evidence must come from the private Field gateway")

        media_contract = AUDIT_BINDABLE_MEDIA.get(str(field_receipt.media_type))
        if media_contract is None:
            raise AuditRepositoryError(
                "Audit binding accepts only sanitized image/jpeg or governed video/mp4 evidence"
            )
        media_kind, frame_count, processed_frame_count = media_contract

        if not field_receipt.sha256 or len(field_receipt.sha256) != 64:
            raise AuditRepositoryError("private evidence receipt has no valid server hash")
        if not field_receipt.storage_receipt_hash or len(field_receipt.storage_receipt_hash) != 64:
            raise AuditRepositoryError("private evidence receipt has no valid gateway receipt hash")
        if not field_receipt.byte_size or field_receipt.byte_size <= 0:
            raise AuditRepositoryError("private evidence receipt has no valid server byte size")

        canonical_ref = f"field-evidence-receipt:{field_receipt.receipt_id}"
        existing_result = await connection.execute(
            text(
                """
                SELECT id, field_evidence_receipt_id, media_kind, source_fingerprint,
                       redacted_evidence_ref, redacted_object_sha256,
                       redacted_object_byte_size, privacy_policy_version,
                       detector_model_ref, frame_count, processed_frame_count, created_at
                FROM audit_redaction_receipts
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND audit_run_id = CAST(:audit_run_id AS UUID)
                  AND field_evidence_receipt_id = CAST(:field_evidence_receipt_id AS UUID)
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "field_evidence_receipt_id": str(field_receipt.receipt_id),
            },
        )
        existing = existing_result.first()
        if existing:
            if existing.source_fingerprint != source_fingerprint:
                raise AuditConflictError(
                    "private evidence receipt is already bound to different source provenance"
                )
            if (
                existing.media_kind != media_kind
                or existing.redacted_evidence_ref != canonical_ref
                or existing.redacted_object_sha256 != field_receipt.sha256
                or existing.redacted_object_byte_size != field_receipt.byte_size
                or existing.frame_count != frame_count
                or existing.processed_frame_count != processed_frame_count
            ):
                raise AuditConflictError(
                    "private evidence receipt no longer matches immutable Audit binding integrity"
                )
            return {
                **_dict(existing),
                "field_evidence_receipt_id": str(field_receipt.receipt_id),
                "field_key": field_receipt.field_key,
                "redacted_object_hash_verified": True,
                "source_fingerprint_verified": False,
                "client_redaction_claim_only": True,
                "server_privacy_verified": False,
                "vision_inference_authorized": False,
                "idempotent_replay": True,
            }

        insert_result = await connection.execute(
            text(
                """
                INSERT INTO audit_redaction_receipts (
                    tenant_id, audit_run_id, location_id, device_id,
                    media_kind, source_fingerprint, redacted_evidence_ref,
                    privacy_policy_version, detector_model_ref,
                    frame_count, processed_frame_count,
                    field_evidence_receipt_id, redacted_object_sha256,
                    redacted_object_byte_size
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:audit_run_id AS UUID),
                    :location_id, :device_id, :media_kind, :source_fingerprint,
                    :redacted_evidence_ref, :privacy_policy_version,
                    :detector_model_ref, :frame_count, :processed_frame_count,
                    CAST(:field_evidence_receipt_id AS UUID), :redacted_object_sha256,
                    :redacted_object_byte_size
                )
                RETURNING id, audit_run_id, location_id, device_id,
                          media_kind, source_fingerprint, redacted_evidence_ref,
                          privacy_policy_version, detector_model_ref,
                          frame_count, processed_frame_count,
                          field_evidence_receipt_id, redacted_object_sha256,
                          redacted_object_byte_size, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "location_id": run.location_id,
                "device_id": device_id,
                "media_kind": media_kind,
                "source_fingerprint": source_fingerprint,
                "redacted_evidence_ref": canonical_ref,
                "privacy_policy_version": privacy_policy_version,
                "detector_model_ref": detector_model_ref,
                "frame_count": frame_count,
                "processed_frame_count": processed_frame_count,
                "field_evidence_receipt_id": str(field_receipt.receipt_id),
                "redacted_object_sha256": field_receipt.sha256,
                "redacted_object_byte_size": field_receipt.byte_size,
            },
        )
        bound = _dict(insert_result.one())
        return {
            **bound,
            "field_evidence_receipt_id": str(field_receipt.receipt_id),
            "field_key": field_receipt.field_key,
            "redacted_object_hash_verified": True,
            "source_fingerprint_verified": False,
            "client_redaction_claim_only": True,
            "server_privacy_verified": False,
            "vision_inference_authorized": False,
            "idempotent_replay": False,
        }
