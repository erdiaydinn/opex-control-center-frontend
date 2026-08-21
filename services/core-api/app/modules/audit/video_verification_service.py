from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import text

from app.core.resources import engine
from app.modules.field_intelligence.repository import _set_tenant
from app.modules.field_intelligence.video_object_read import read_private_video_object

from .privacy_verification_runtime import AuditPrivacyEvidenceScanner
from .repository import AuditRepositoryError
from .video_verification_runtime import (
    AuditCanonicalVideoManifest,
    AuditPrivateVideoDecoder,
    AuditVideoVerificationRuntime,
)

VIDEO_VERIFICATION_AUTHORITY_VERSION = "server_video_privacy_v1"
VIDEO_VERIFIER_REF = "eay-audit-video-privacy-orchestrator-v1"


def _dict(row) -> dict[str, object]:
    return dict(row._mapping)


def _frame_manifest(manifest: AuditCanonicalVideoManifest) -> list[dict[str, object]]:
    return [
        {
            "sequence": frame.sequence,
            "timestamp_ms": frame.timestamp_ms,
            "sha256": frame.sha256,
            "byte_size": frame.byte_size,
            "privacy_verification_fingerprint": frame.privacy_verification_fingerprint,
        }
        for frame in manifest.frames
    ]


def _verification_fingerprint(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    redaction_receipt_id: UUID,
    manifest: AuditCanonicalVideoManifest,
) -> str:
    payload = {
        "audit_run_id": str(audit_run_id),
        "authority_version": VIDEO_VERIFICATION_AUTHORITY_VERSION,
        "canonical_frame_count": manifest.canonical_frame_count,
        "decoder_fingerprint": manifest.decoder_fingerprint,
        "decoder_ref": manifest.decoder_ref,
        "duration_ms": manifest.duration_ms,
        "frames": _frame_manifest(manifest),
        "manifest_fingerprint": manifest.manifest_fingerprint,
        "processed_frame_count": manifest.processed_frame_count,
        "reason": manifest.reason,
        "redaction_receipt_id": str(redaction_receipt_id),
        "source_byte_size": manifest.source_byte_size,
        "source_sha256": manifest.source_sha256,
        "status": manifest.status,
        "tenant_id": tenant_id,
        "verifier_ref": VIDEO_VERIFIER_REF,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _load_bound_video_receipt(
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
                SELECT redaction.id, redaction.audit_run_id, redaction.location_id,
                       redaction.media_kind, redaction.field_evidence_receipt_id,
                       redaction.redacted_evidence_ref,
                       redaction.redacted_object_sha256,
                       redaction.redacted_object_byte_size,
                       run.field_mission_id AS run_mission_id,
                       run.status AS run_status,
                       field.receipt_id AS field_receipt_id,
                       field.mission_id AS field_mission_id,
                       field.location_id AS field_location_id,
                       field.media_type, field.sha256 AS field_sha256,
                       field.byte_size AS field_byte_size,
                       field.storage_provider, field.storage_receipt_hash,
                       field.expires_at
                FROM audit_redaction_receipts redaction
                JOIN audit_runs run
                  ON run.tenant_id = redaction.tenant_id
                 AND run.id = redaction.audit_run_id
                JOIN field_evidence_object_receipts field
                  ON field.tenant_id = redaction.tenant_id
                 AND field.receipt_id = redaction.field_evidence_receipt_id
                WHERE redaction.tenant_id = CAST(:tenant_id AS UUID)
                  AND redaction.audit_run_id = CAST(:audit_run_id AS UUID)
                  AND redaction.id = CAST(:redaction_receipt_id AS UUID)
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
        row = result.first()
        if row is None:
            raise AuditRepositoryError("active bound video evidence was not found")
        bound = _dict(row)

    if bound["run_status"] == "cancelled":
        raise AuditRepositoryError("cancelled audit run cannot verify video evidence")
    if bound["run_mission_id"] is None or str(bound["run_mission_id"]) != str(
        bound["field_mission_id"]
    ):
        raise AuditRepositoryError("video evidence mission authority is invalid")
    if str(bound["location_id"]) != str(bound["field_location_id"]):
        raise AuditRepositoryError("video evidence location authority is invalid")
    if bound["media_kind"] != "video" or bound["media_type"] != "video/mp4":
        raise AuditRepositoryError("video verification requires a governed video/mp4 binding")
    if bound["storage_provider"] != "private_gateway":
        raise AuditRepositoryError("video evidence must come from the private Field gateway")
    if not bound["storage_receipt_hash"] or len(str(bound["storage_receipt_hash"])) != 64:
        raise AuditRepositoryError("video storage receipt authority is invalid")
    if (
        bound["redacted_object_sha256"] != bound["field_sha256"]
        or bound["redacted_object_byte_size"] != bound["field_byte_size"]
        or bound["redacted_evidence_ref"]
        != f"field-evidence-receipt:{bound['field_receipt_id']}"
    ):
        raise AuditRepositoryError("bound video evidence no longer matches immutable Field receipt")
    return bound


async def verify_bound_video_receipt(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    redaction_receipt_id: UUID,
    decoder: AuditPrivateVideoDecoder,
    scanner: AuditPrivacyEvidenceScanner,
) -> dict[str, object]:
    """Create append-only server video privacy authority from immutable private MP4 bytes."""

    bound = await _load_bound_video_receipt(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        redaction_receipt_id=redaction_receipt_id,
    )
    content = await read_private_video_object(
        tenant_id=tenant_id,
        receipt_id=str(bound["field_receipt_id"]),
        expected_byte_size=int(bound["field_byte_size"]),
    )
    manifest = AuditVideoVerificationRuntime().verify_mp4(
        content=content,
        expected_sha256=str(bound["field_sha256"]),
        expected_byte_size=int(bound["field_byte_size"]),
        decoder=decoder,
        scanner=scanner,
    )
    verification_fingerprint = _verification_fingerprint(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        redaction_receipt_id=redaction_receipt_id,
        manifest=manifest,
    )

    current = await _load_bound_video_receipt(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        redaction_receipt_id=redaction_receipt_id,
    )
    if (
        current["field_sha256"] != bound["field_sha256"]
        or current["field_byte_size"] != bound["field_byte_size"]
        or current["field_receipt_id"] != bound["field_receipt_id"]
    ):
        raise AuditRepositoryError("video binding changed during server verification")

    frame_manifest = _frame_manifest(manifest)
    parameters = {
        "tenant_id": tenant_id,
        "redaction_receipt_id": str(redaction_receipt_id),
        "verification_status": manifest.status,
        "verifier_ref": VIDEO_VERIFIER_REF,
        "authority_version": VIDEO_VERIFICATION_AUTHORITY_VERSION,
        "verification_fingerprint": verification_fingerprint,
        "reason": manifest.reason,
        "observed_sha256": manifest.source_sha256,
        "observed_byte_size": manifest.source_byte_size,
        "decoder_ref": manifest.decoder_ref,
        "decoder_fingerprint": manifest.decoder_fingerprint,
        "duration_ms": manifest.duration_ms,
        "canonical_frame_count": manifest.canonical_frame_count,
        "processed_frame_count": manifest.processed_frame_count,
        "manifest_fingerprint": manifest.manifest_fingerprint,
        "frame_manifest": json.dumps(frame_manifest, separators=(",", ":")),
    }
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        existing_result = await connection.execute(
            text(
                """
                SELECT *
                FROM audit_video_verification_events
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND verification_fingerprint = :verification_fingerprint
                LIMIT 1
                """
            ),
            parameters,
        )
        existing = existing_result.first()
        if existing is not None:
            return {
                **_dict(existing),
                "privacy_gate_passed": manifest.privacy_gate_passed,
                "vision_inference_authorized": False,
                "idempotent_replay": True,
            }

        insert_result = await connection.execute(
            text(
                """
                INSERT INTO audit_video_verification_events (
                    tenant_id, redaction_receipt_id, verification_status,
                    verifier_ref, verification_authority_version,
                    verification_fingerprint, reason, observed_sha256,
                    observed_byte_size, decoder_ref, decoder_fingerprint,
                    duration_ms, canonical_frame_count, processed_frame_count,
                    manifest_fingerprint, frame_manifest
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:redaction_receipt_id AS UUID),
                    :verification_status, :verifier_ref, :authority_version,
                    :verification_fingerprint, :reason, :observed_sha256,
                    :observed_byte_size, :decoder_ref, :decoder_fingerprint,
                    :duration_ms, :canonical_frame_count, :processed_frame_count,
                    :manifest_fingerprint, CAST(:frame_manifest AS JSONB)
                )
                ON CONFLICT (tenant_id, verification_fingerprint) DO NOTHING
                RETURNING *
                """
            ),
            parameters,
        )
        inserted = insert_result.first()
        if inserted is None:
            race_result = await connection.execute(
                text(
                    """
                    SELECT *
                    FROM audit_video_verification_events
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                      AND verification_fingerprint = :verification_fingerprint
                    LIMIT 1
                    """
                ),
                parameters,
            )
            inserted = race_result.first()
            if inserted is None:
                raise AuditRepositoryError("video verification replay fence failed closed")
            idempotent_replay = True
        else:
            idempotent_replay = False
        event = _dict(inserted)
    return {
        **event,
        "privacy_gate_passed": manifest.privacy_gate_passed,
        "vision_inference_authorized": False,
        "idempotent_replay": idempotent_replay,
    }
