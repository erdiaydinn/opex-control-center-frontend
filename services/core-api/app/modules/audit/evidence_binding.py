from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from app.core.resources import engine
from app.modules.field_intelligence.repository import _set_tenant

from .repository import AuditConflictError, AuditRepositoryError


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
    """Bind a client redaction claim to a server-issued private evidence receipt.

    The client cannot choose the canonical redacted evidence reference. The server resolves the
    Field evidence receipt and proves it belongs to the same Audit run mission/location before
    creating the Audit redaction receipt. This does *not* verify the raw source fingerprint and
    does not authorize AI inference.
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
                SELECT id, mission_id, location_id, field_key, media_type,
                       sha256, byte_size, storage_provider, storage_key,
                       client_submission_id, created_at
                FROM field_evidence_object_receipts
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:field_evidence_receipt_id AS UUID)
                  AND mission_id = CAST(:mission_id AS UUID)
                  AND location_id = :location_id
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
                "private evidence receipt does not belong to this audit run mission/location"
            )
        if field_receipt.media_type != "image/jpeg":
            raise AuditRepositoryError(
                "Audit redaction binding currently accepts sanitized image/jpeg evidence only"
            )
        if not field_receipt.sha256 or len(field_receipt.sha256) != 64:
            raise AuditRepositoryError("private evidence receipt has no valid server hash")
        if not field_receipt.byte_size or field_receipt.byte_size <= 0:
            raise AuditRepositoryError("private evidence receipt has no valid server byte size")

        canonical_ref = f"field-evidence-receipt:{field_receipt.id}"
        existing_result = await connection.execute(
            text(
                """
                SELECT id, source_fingerprint, redacted_evidence_ref,
                       privacy_policy_version, detector_model_ref,
                       frame_count, processed_frame_count, created_at
                FROM audit_redaction_receipts
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND audit_run_id = CAST(:audit_run_id AS UUID)
                  AND redacted_evidence_ref = :redacted_evidence_ref
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "redacted_evidence_ref": canonical_ref,
            },
        )
        existing = existing_result.first()
        if existing:
            if existing.source_fingerprint != source_fingerprint:
                raise AuditConflictError(
                    "private evidence receipt is already bound to different source provenance"
                )
            return {
                **_dict(existing),
                "field_evidence_receipt_id": str(field_receipt.id),
                "redacted_object_sha256": field_receipt.sha256,
                "redacted_object_byte_size": field_receipt.byte_size,
                "redacted_object_hash_verified": True,
                "source_fingerprint_verified": False,
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
                    frame_count, processed_frame_count
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:audit_run_id AS UUID),
                    :location_id, :device_id, 'image', :source_fingerprint,
                    :redacted_evidence_ref, :privacy_policy_version,
                    :detector_model_ref, 1, 1
                )
                RETURNING id, audit_run_id, location_id, device_id,
                          media_kind, source_fingerprint, redacted_evidence_ref,
                          privacy_policy_version, detector_model_ref,
                          frame_count, processed_frame_count, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "location_id": run.location_id,
                "device_id": device_id,
                "source_fingerprint": source_fingerprint,
                "redacted_evidence_ref": canonical_ref,
                "privacy_policy_version": privacy_policy_version,
                "detector_model_ref": detector_model_ref,
            },
        )
        bound = _dict(insert_result.one())
        return {
            **bound,
            "field_evidence_receipt_id": str(field_receipt.id),
            "field_key": field_receipt.field_key,
            "redacted_object_sha256": field_receipt.sha256,
            "redacted_object_byte_size": field_receipt.byte_size,
            "redacted_object_hash_verified": True,
            "source_fingerprint_verified": False,
            "server_privacy_verified": False,
            "vision_inference_authorized": False,
            "idempotent_replay": False,
        }
