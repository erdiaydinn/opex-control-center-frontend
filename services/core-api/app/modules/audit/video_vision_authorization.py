from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.ai_core.substrate_contract import REQUIRED_CONSUMERS
from app.core.resources import engine
from app.modules.field_intelligence.repository import _set_tenant

from .control_contracts import (
    AuditQuestionControl,
    parse_question_controls,
    question_control_fingerprint,
)
from .field_activation_proof import (
    AuditFieldActivationProof,
    AuditFieldActivationProofUnavailable,
    AuditFieldActivationProofVerifier,
    require_field_activation_for_production,
)
from .repository import AuditConflictError, AuditRepositoryError
from .video_verification_runtime import (
    AuditCanonicalVideoFrame,
    AuditCanonicalVideoManifest,
)
from .video_verification_service import VIDEO_VERIFICATION_AUTHORITY_VERSION
from .video_verification_service import (
    _verification_fingerprint as video_verification_fingerprint,
)
from .vision_model_proof import (
    ProductionModelProof,
    ProductionModelProofUnavailable,
    ProductionModelProofVerifier,
    configured_production_model_proof_verifier,
)

AUTHORIZATION_TTL_MINUTES = 5


@dataclass(frozen=True)
class VideoVisionAuthorizationDecision:
    status: str
    reason: str
    authorization_id: str | None = None
    authorization_fingerprint: str | None = None
    expires_at: object | None = None
    model_record_id: str | None = None
    capabilities: tuple[str, ...] = ()
    vision_inference_authorized: bool = False
    finding_authorized: bool = False
    action_authorized: bool = False


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _find_item_control(
    *,
    settings: dict[str, object],
    item_key: str,
) -> AuditQuestionControl | None:
    controls = parse_question_controls(settings)
    return next((control for control in controls if control.item_key == item_key), None)


def _field_activation_fingerprint(proof: AuditFieldActivationProof | None) -> str | None:
    if proof is None:
        return None
    return _canonical_sha256(proof.model_dump())


def _manifest_fingerprint_from_context(context: dict[str, object]) -> str | None:
    frames = context.get("frame_manifest")
    if not isinstance(frames, list):
        return None
    canonical_frames: list[dict[str, object]] = []
    previous_timestamp = -1
    for expected_sequence, frame in enumerate(frames):
        if not isinstance(frame, dict):
            return None
        try:
            sequence = int(frame["sequence"])
            timestamp_ms = int(frame["timestamp_ms"])
            sha256 = str(frame["sha256"])
            byte_size = int(frame["byte_size"])
            privacy_fingerprint = str(frame["privacy_verification_fingerprint"])
        except (KeyError, TypeError, ValueError):
            return None
        if (
            sequence != expected_sequence
            or timestamp_ms <= previous_timestamp
            or timestamp_ms < 0
            or byte_size <= 0
            or len(sha256) != 64
            or len(privacy_fingerprint) != 64
        ):
            return None
        canonical_frames.append(
            {
                "byte_size": byte_size,
                "privacy_verification_fingerprint": privacy_fingerprint,
                "sequence": sequence,
                "sha256": sha256,
                "timestamp_ms": timestamp_ms,
            }
        )
        previous_timestamp = timestamp_ms

    payload = {
        "decoder_fingerprint": context.get("decoder_fingerprint"),
        "decoder_ref": context.get("decoder_ref"),
        "duration_ms": context.get("duration_ms"),
        "frames": canonical_frames,
        "source_byte_size": context.get("observed_byte_size"),
        "source_sha256": context.get("observed_sha256"),
    }
    return _canonical_sha256(payload)


async def _load_context(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    item_key: str,
    redaction_receipt_id: UUID,
    video_verification_event_id: UUID,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT run.id AS audit_run_id,
                       run.program_key,
                       run.program_version,
                       run.status AS run_status,
                       program.settings,
                       redaction.id AS redaction_receipt_id,
                       redaction.media_kind,
                       redaction.redacted_object_sha256,
                       redaction.redacted_object_byte_size,
                       verification.id AS video_verification_event_id,
                       verification.verification_status,
                       verification.verifier_ref,
                       verification.verification_authority_version,
                       verification.verification_fingerprint,
                       verification.reason AS verification_reason,
                       verification.observed_sha256,
                       verification.observed_byte_size,
                       verification.decoder_ref,
                       verification.decoder_fingerprint,
                       verification.duration_ms,
                       verification.canonical_frame_count,
                       verification.processed_frame_count,
                       verification.manifest_fingerprint,
                       verification.frame_manifest
                FROM audit_runs run
                JOIN audit_program_versions program
                  ON program.tenant_id = run.tenant_id
                 AND program.program_key = run.program_key
                 AND program.version = run.program_version
                JOIN audit_redaction_receipts redaction
                  ON redaction.tenant_id = run.tenant_id
                 AND redaction.audit_run_id = run.id
                JOIN audit_video_verification_events verification
                  ON verification.tenant_id = redaction.tenant_id
                 AND verification.redaction_receipt_id = redaction.id
                WHERE run.tenant_id = CAST(:tenant_id AS UUID)
                  AND run.id = CAST(:audit_run_id AS UUID)
                  AND redaction.id = CAST(:redaction_receipt_id AS UUID)
                  AND verification.id = CAST(:video_verification_event_id AS UUID)
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "redaction_receipt_id": str(redaction_receipt_id),
                "video_verification_event_id": str(video_verification_event_id),
            },
        )
        row = result.mappings().first()
    if row is None:
        raise AuditRepositoryError("Audit video vision authorization context not found")
    context = dict(row)
    context["tenant_id"] = tenant_id
    context["item_key"] = item_key
    return context


def _video_event_is_current_and_intact(context: dict[str, object]) -> bool:
    if context.get("verification_status") != "verified":
        return False
    if context.get("verification_authority_version") != VIDEO_VERIFICATION_AUTHORITY_VERSION:
        return False
    if context.get("media_kind") != "video":
        return False
    if context.get("observed_sha256") != context.get("redacted_object_sha256"):
        return False
    if context.get("observed_byte_size") != context.get("redacted_object_byte_size"):
        return False
    if not context.get("decoder_ref") or not context.get("decoder_fingerprint"):
        return False
    if not context.get("manifest_fingerprint"):
        return False
    try:
        canonical_frame_count = int(context["canonical_frame_count"])
        processed_frame_count = int(context["processed_frame_count"])
        duration_ms = int(context["duration_ms"])
    except (KeyError, TypeError, ValueError):
        return False
    if (
        canonical_frame_count <= 0
        or processed_frame_count != canonical_frame_count
        or duration_ms <= 0
    ):
        return False
    if _manifest_fingerprint_from_context(context) != context.get("manifest_fingerprint"):
        return False

    raw_frames = context.get("frame_manifest")
    if not isinstance(raw_frames, list) or len(raw_frames) != canonical_frame_count:
        return False
    try:
        frames = tuple(
            AuditCanonicalVideoFrame(
                sequence=int(frame["sequence"]),
                timestamp_ms=int(frame["timestamp_ms"]),
                sha256=str(frame["sha256"]),
                byte_size=int(frame["byte_size"]),
                privacy_verification_fingerprint=str(
                    frame["privacy_verification_fingerprint"]
                ),
            )
            for frame in raw_frames
            if isinstance(frame, dict)
        )
        if len(frames) != canonical_frame_count:
            return False
        manifest = AuditCanonicalVideoManifest(
            status="verified",
            reason=str(context.get("verification_reason") or ""),
            source_sha256=str(context["observed_sha256"]),
            source_byte_size=int(context["observed_byte_size"]),
            duration_ms=duration_ms,
            canonical_frame_count=canonical_frame_count,
            processed_frame_count=processed_frame_count,
            decoder_ref=str(context["decoder_ref"]),
            decoder_fingerprint=str(context["decoder_fingerprint"]),
            frames=frames,
            manifest_fingerprint=str(context["manifest_fingerprint"]),
            privacy_gate_passed=True,
        )
    except (KeyError, TypeError, ValueError):
        return False

    expected_event_fingerprint = video_verification_fingerprint(
        tenant_id=str(context["tenant_id"]),
        audit_run_id=UUID(str(context["audit_run_id"])),
        redaction_receipt_id=UUID(str(context["redaction_receipt_id"])),
        manifest=manifest,
    )
    return expected_event_fingerprint == context.get("verification_fingerprint")


def _authorization_fingerprint(
    *,
    tenant_id: str,
    context: dict[str, object],
    item_key: str,
    control_fingerprint: str,
    proof: ProductionModelProof,
    capabilities: tuple[str, ...],
    field_activation_fingerprint: str | None,
) -> str:
    return _canonical_sha256(
        {
            "tenant_id": tenant_id,
            "audit_run_id": str(context["audit_run_id"]),
            "item_key": item_key,
            "redaction_receipt_id": str(context["redaction_receipt_id"]),
            "video_verification_event_id": str(context["video_verification_event_id"]),
            "video_verification_fingerprint": str(context["verification_fingerprint"]),
            "video_manifest_fingerprint": str(context["manifest_fingerprint"]),
            "decoder_fingerprint": str(context["decoder_fingerprint"]),
            "program_key": str(context["program_key"]),
            "program_version": int(context["program_version"]),
            "question_control_fingerprint": control_fingerprint,
            "model_record_id": proof.model_record_id,
            "artifact_sha256": proof.artifact_sha256,
            "artifact_provenance_fingerprint": proof.artifact_provenance_fingerprint,
            "production_promotion_fingerprint": proof.production_promotion_fingerprint,
            "production_release_proof_fingerprint": proof.production_release_proof_fingerprint,
            "field_activation_fingerprint": field_activation_fingerprint,
            "capabilities": list(capabilities),
        }
    )


async def authorize_video_vision_inference(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    item_key: str,
    redaction_receipt_id: UUID,
    video_verification_event_id: UUID,
    model_proof_verifier: ProductionModelProofVerifier | None = None,
    field_activation_proof_verifier: AuditFieldActivationProofVerifier | None = None,
) -> VideoVisionAuthorizationDecision:
    """Issue one model-execution lease from verified video evidence without
    granting Audit truth authority."""

    if "audit" not in REQUIRED_CONSUMERS:
        return VideoVisionAuthorizationDecision(
            "blocked",
            "audit_not_authorized_ai_substrate_consumer",
        )
    if not item_key.strip() or len(item_key) > 180:
        return VideoVisionAuthorizationDecision("blocked", "invalid_audit_item_key")

    context = await _load_context(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        item_key=item_key,
        redaction_receipt_id=redaction_receipt_id,
        video_verification_event_id=video_verification_event_id,
    )
    if context["run_status"] == "cancelled":
        return VideoVisionAuthorizationDecision("blocked", "audit_run_cancelled")
    if not _video_event_is_current_and_intact(context):
        return VideoVisionAuthorizationDecision(
            "blocked",
            "server_video_privacy_v1_verification_required",
        )

    settings = context["settings"]
    if not isinstance(settings, dict):
        return VideoVisionAuthorizationDecision("blocked", "audit_program_settings_invalid")
    try:
        control = _find_item_control(settings=settings, item_key=item_key)
    except (TypeError, ValueError):
        return VideoVisionAuthorizationDecision("blocked", "audit_question_control_invalid")
    if control is None:
        return VideoVisionAuthorizationDecision("blocked", "audit_question_control_missing")
    if "VIDEO" not in control.evidence_modalities:
        return VideoVisionAuthorizationDecision("blocked", "video_evidence_not_permitted_for_item")
    vision = control.vision_contract
    if vision is None:
        return VideoVisionAuthorizationDecision("blocked", "vision_contract_missing_for_item")

    try:
        field_activation = await require_field_activation_for_production(
            tenant_id=tenant_id,
            capability="video_vision",
            verifier=field_activation_proof_verifier,
        )
    except AuditFieldActivationProofUnavailable:
        return VideoVisionAuthorizationDecision(
            "blocked",
            "current_production_video_activation_proof_unavailable",
        )
    if (
        field_activation is not None
        and field_activation.video_decoder_fingerprint != context["decoder_fingerprint"]
    ):
        return VideoVisionAuthorizationDecision(
            "blocked",
            "production_video_decoder_fingerprint_mismatch",
        )

    verifier = model_proof_verifier or configured_production_model_proof_verifier()
    try:
        proof = await verifier.require_current_production(vision.model_record_id)
    except (KeyError, ValueError, ProductionModelProofUnavailable):
        return VideoVisionAuthorizationDecision(
            "blocked",
            "current_production_model_proof_unavailable",
        )
    if proof.model_record_id != vision.model_record_id:
        return VideoVisionAuthorizationDecision(
            "blocked",
            "production_model_proof_identity_mismatch",
        )

    capabilities = tuple(sorted(vision.required_capabilities))
    control_fingerprint = question_control_fingerprint(control)
    activation_fingerprint = _field_activation_fingerprint(field_activation)
    auth_fingerprint = _authorization_fingerprint(
        tenant_id=tenant_id,
        context=context,
        item_key=item_key,
        control_fingerprint=control_fingerprint,
        proof=proof,
        capabilities=capabilities,
        field_activation_fingerprint=activation_fingerprint,
    )

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        existing = await connection.execute(
            text(
                """
                SELECT id, expires_at, consumed_at
                FROM audit_video_inference_authorizations
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND authorization_fingerprint = :authorization_fingerprint
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "authorization_fingerprint": auth_fingerprint},
        )
        existing_row = existing.mappings().first()
        if existing_row is not None:
            if existing_row["consumed_at"] is not None:
                return VideoVisionAuthorizationDecision(
                    "blocked",
                    "video_vision_authorization_already_consumed",
                )
            validity = await connection.execute(
                text("SELECT :expires_at > CURRENT_TIMESTAMP AS valid"),
                {"expires_at": existing_row["expires_at"]},
            )
            if not bool(validity.scalar_one()):
                return VideoVisionAuthorizationDecision(
                    "blocked",
                    "video_vision_authorization_expired",
                )
            return VideoVisionAuthorizationDecision(
                status="authorized",
                reason="existing_single_use_video_authorization",
                authorization_id=str(existing_row["id"]),
                authorization_fingerprint=auth_fingerprint,
                expires_at=existing_row["expires_at"],
                model_record_id=proof.model_record_id,
                capabilities=capabilities,
                vision_inference_authorized=True,
            )

        try:
            inserted = await connection.execute(
                text(
                    """
                    INSERT INTO audit_video_inference_authorizations (
                        tenant_id, audit_run_id, item_key,
                        redaction_receipt_id, video_verification_event_id,
                        program_key, program_version, question_control_fingerprint,
                        model_record_id, artifact_sha256, artifact_provenance_fingerprint,
                        production_promotion_fingerprint, production_release_proof_fingerprint,
                        video_manifest_fingerprint, decoder_fingerprint,
                        field_activation_fingerprint, capabilities,
                        authorization_fingerprint, expires_at
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:audit_run_id AS UUID), :item_key,
                        CAST(:redaction_receipt_id AS UUID),
                        CAST(:video_verification_event_id AS UUID),
                        :program_key, :program_version, :question_control_fingerprint,
                        :model_record_id, :artifact_sha256, :artifact_provenance_fingerprint,
                        :production_promotion_fingerprint, :production_release_proof_fingerprint,
                        :video_manifest_fingerprint, :decoder_fingerprint,
                        :field_activation_fingerprint, CAST(:capabilities AS JSONB),
                        :authorization_fingerprint,
                        CURRENT_TIMESTAMP + interval '5 minutes'
                    )
                    RETURNING id, expires_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "audit_run_id": str(audit_run_id),
                    "item_key": item_key,
                    "redaction_receipt_id": str(redaction_receipt_id),
                    "video_verification_event_id": str(video_verification_event_id),
                    "program_key": str(context["program_key"]),
                    "program_version": int(context["program_version"]),
                    "question_control_fingerprint": control_fingerprint,
                    "model_record_id": proof.model_record_id,
                    "artifact_sha256": proof.artifact_sha256,
                    "artifact_provenance_fingerprint": proof.artifact_provenance_fingerprint,
                    "production_promotion_fingerprint": proof.production_promotion_fingerprint,
                    "production_release_proof_fingerprint": (
                        proof.production_release_proof_fingerprint
                    ),
                    "video_manifest_fingerprint": str(context["manifest_fingerprint"]),
                    "decoder_fingerprint": str(context["decoder_fingerprint"]),
                    "field_activation_fingerprint": activation_fingerprint,
                    "capabilities": json.dumps(list(capabilities), separators=(",", ":")),
                    "authorization_fingerprint": auth_fingerprint,
                },
            )
        except IntegrityError as exc:
            raise AuditConflictError("video vision authorization collision") from exc
        row = inserted.mappings().one()

    return VideoVisionAuthorizationDecision(
        status="authorized",
        reason="video_privacy_model_and_field_authorities_passed",
        authorization_id=str(row["id"]),
        authorization_fingerprint=auth_fingerprint,
        expires_at=row["expires_at"],
        model_record_id=proof.model_record_id,
        capabilities=capabilities,
        vision_inference_authorized=True,
    )


async def consume_video_vision_authorization(
    *,
    tenant_id: str,
    authorization_id: UUID,
    authorization_fingerprint: str,
) -> dict[str, object]:
    """Atomically consume one exact video inference lease immediately before model execution."""

    if len(authorization_fingerprint) != 64:
        raise AuditRepositoryError("invalid video vision authorization fingerprint")
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                UPDATE audit_video_inference_authorizations authorization
                SET consumed_at = CURRENT_TIMESTAMP
                FROM audit_runs run,
                     audit_video_verification_events verification
                WHERE authorization.tenant_id = CAST(:tenant_id AS UUID)
                  AND authorization.id = CAST(:authorization_id AS UUID)
                  AND authorization.authorization_fingerprint = :authorization_fingerprint
                  AND authorization.consumed_at IS NULL
                  AND authorization.expires_at > CURRENT_TIMESTAMP
                  AND run.tenant_id = authorization.tenant_id
                  AND run.id = authorization.audit_run_id
                  AND run.status <> 'cancelled'
                  AND verification.tenant_id = authorization.tenant_id
                  AND verification.id = authorization.video_verification_event_id
                  AND verification.verification_status = 'verified'
                  AND verification.verification_authority_version = :authority_version
                  AND verification.manifest_fingerprint = authorization.video_manifest_fingerprint
                  AND verification.decoder_fingerprint = authorization.decoder_fingerprint
                RETURNING authorization.id, authorization.audit_run_id,
                          authorization.item_key, authorization.model_record_id,
                          authorization.capabilities,
                          authorization.authorization_fingerprint,
                          authorization.consumed_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "authorization_id": str(authorization_id),
                "authorization_fingerprint": authorization_fingerprint,
                "authority_version": VIDEO_VERIFICATION_AUTHORITY_VERSION,
            },
        )
        row = result.mappings().first()
    if row is None:
        raise AuditConflictError(
            "video vision authorization is expired, consumed, revoked by context, or invalid"
        )
    return {
        **dict(row),
        "vision_inference_authorized": True,
        "finding_authorized": False,
        "action_authorized": False,
    }
