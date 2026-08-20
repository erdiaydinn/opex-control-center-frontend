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
from .privacy_verification_runtime import (
    AuditPrivacyScanResult,
    AuditServerPrivacyVerification,
)
from .privacy_verification_service import (
    SERVER_PRIVACY_AUTHORITY_VERSION,
)
from .privacy_verification_service import (
    _fingerprint as privacy_verification_fingerprint,
)
from .repository import AuditConflictError, AuditRepositoryError
from .vision_model_proof import (
    ProductionModelProof,
    ProductionModelProofUnavailable,
    ProductionModelProofVerifier,
    configured_production_model_proof_verifier,
)

AUTHORIZATION_TTL_MINUTES = 5


@dataclass(frozen=True)
class VisionAuthorizationDecision:
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


async def _load_context(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    item_key: str,
    redaction_receipt_id: UUID,
    privacy_verification_event_id: UUID,
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
                       redaction.field_evidence_receipt_id,
                       redaction.media_kind,
                       redaction.redacted_object_sha256,
                       redaction.redacted_object_byte_size,
                       verification.id AS privacy_verification_event_id,
                       verification.verification_status,
                       verification.verifier_ref,
                       verification.verification_authority_version,
                       verification.verification_fingerprint,
                       verification.reason AS verification_reason,
                       verification.observed_sha256,
                       verification.observed_byte_size,
                       verification.scanner_model_ref,
                       verification.scanner_model_fingerprint,
                       verification.detected_face_count,
                       verification.detected_sensitive_region_count
                FROM audit_runs run
                JOIN audit_program_versions program
                  ON program.tenant_id=run.tenant_id
                 AND program.program_key=run.program_key
                 AND program.version=run.program_version
                JOIN audit_redaction_receipts redaction
                  ON redaction.tenant_id=run.tenant_id
                 AND redaction.audit_run_id=run.id
                JOIN audit_redaction_verification_events verification
                  ON verification.tenant_id=redaction.tenant_id
                 AND verification.redaction_receipt_id=redaction.id
                WHERE run.tenant_id=CAST(:tenant_id AS UUID)
                  AND run.id=CAST(:audit_run_id AS UUID)
                  AND redaction.id=CAST(:redaction_receipt_id AS UUID)
                  AND verification.id=CAST(:privacy_verification_event_id AS UUID)
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "redaction_receipt_id": str(redaction_receipt_id),
                "privacy_verification_event_id": str(privacy_verification_event_id),
            },
        )
        row = result.mappings().first()
    if row is None:
        raise AuditRepositoryError("Audit vision authorization context not found")
    context = dict(row)
    context["item_key"] = item_key
    return context


def _privacy_event_is_current_and_intact(context: dict[str, object]) -> bool:
    if context["verification_status"] != "verified":
        return False
    if context["verification_authority_version"] != SERVER_PRIVACY_AUTHORITY_VERSION:
        return False
    if context["media_kind"] != "image":
        return False
    if context["observed_sha256"] != context["redacted_object_sha256"]:
        return False
    if context["observed_byte_size"] != context["redacted_object_byte_size"]:
        return False
    if context["detected_face_count"] != 0:
        return False
    if context["detected_sensitive_region_count"] != 0:
        return False
    if not context["scanner_model_ref"] or not context["scanner_model_fingerprint"]:
        return False

    scan = AuditPrivacyScanResult(
        detected_face_count=0,
        detected_sensitive_region_count=0,
        scanner_model_ref=str(context["scanner_model_ref"]),
        scanner_model_fingerprint=str(context["scanner_model_fingerprint"]),
    )
    verification = AuditServerPrivacyVerification(
        status="verified",
        reason=str(context["verification_reason"] or ""),
        observed_sha256=str(context["observed_sha256"]),
        observed_byte_size=int(context["observed_byte_size"]),
        scan=scan,
        privacy_gate_passed=True,
    )
    expected = privacy_verification_fingerprint(
        tenant_id=str(context["tenant_id"]) if "tenant_id" in context else "",
        audit_run_id=UUID(str(context["audit_run_id"])),
        redaction_receipt_id=UUID(str(context["redaction_receipt_id"])),
        field_evidence_receipt_id=UUID(str(context["field_evidence_receipt_id"])),
        expected_sha256=str(context["redacted_object_sha256"]),
        expected_byte_size=int(context["redacted_object_byte_size"]),
        result=verification,
    )
    return expected == context["verification_fingerprint"]


def _field_activation_fingerprint(proof: AuditFieldActivationProof | None) -> str | None:
    if proof is None:
        return None
    return _canonical_sha256(proof.model_dump())


def _authorization_fingerprint(
    *,
    tenant_id: str,
    context: dict[str, object],
    item_key: str,
    control_fingerprint: str,
    proof: ProductionModelProof,
    capabilities: tuple[str, ...],
    field_activation_fingerprint: str | None = None,
) -> str:
    return _canonical_sha256(
        {
            "tenant_id": tenant_id,
            "audit_run_id": str(context["audit_run_id"]),
            "item_key": item_key,
            "redaction_receipt_id": str(context["redaction_receipt_id"]),
            "privacy_verification_event_id": str(context["privacy_verification_event_id"]),
            "privacy_verification_fingerprint": str(context["verification_fingerprint"]),
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


async def authorize_vision_inference(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    item_key: str,
    redaction_receipt_id: UUID,
    privacy_verification_event_id: UUID,
    model_proof_verifier: ProductionModelProofVerifier | None = None,
    field_activation_proof_verifier: AuditFieldActivationProofVerifier | None = None,
) -> VisionAuthorizationDecision:
    """Issue a single-use model-inference receipt without granting Audit truth authority."""

    if "audit" not in REQUIRED_CONSUMERS:
        return VisionAuthorizationDecision("blocked", "audit_not_authorized_ai_substrate_consumer")
    if not item_key.strip() or len(item_key) > 180:
        return VisionAuthorizationDecision("blocked", "invalid_audit_item_key")

    context = await _load_context(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        item_key=item_key,
        redaction_receipt_id=redaction_receipt_id,
        privacy_verification_event_id=privacy_verification_event_id,
    )
    context["tenant_id"] = tenant_id
    if context["run_status"] == "cancelled":
        return VisionAuthorizationDecision("blocked", "audit_run_cancelled")
    if not _privacy_event_is_current_and_intact(context):
        return VisionAuthorizationDecision("blocked", "server_privacy_v2_verification_required")

    settings = context["settings"]
    if not isinstance(settings, dict):
        return VisionAuthorizationDecision("blocked", "audit_program_settings_invalid")
    try:
        control = _find_item_control(settings=settings, item_key=item_key)
    except (TypeError, ValueError):
        return VisionAuthorizationDecision("blocked", "audit_question_control_invalid")
    if control is None:
        return VisionAuthorizationDecision("blocked", "audit_question_control_missing")
    if "VISUAL" not in control.evidence_modalities:
        return VisionAuthorizationDecision("blocked", "visual_evidence_not_permitted_for_item")
    vision = control.vision_contract
    if vision is None:
        return VisionAuthorizationDecision("blocked", "vision_contract_missing_for_item")

    try:
        field_activation = await require_field_activation_for_production(
            tenant_id=tenant_id,
            capability="photo_vision",
            verifier=field_activation_proof_verifier,
        )
    except AuditFieldActivationProofUnavailable:
        return VisionAuthorizationDecision(
            "blocked",
            "current_production_field_activation_proof_unavailable",
        )

    verifier = model_proof_verifier or configured_production_model_proof_verifier()
    try:
        proof = await verifier.require_current_production(vision.model_record_id)
    except (KeyError, ValueError, ProductionModelProofUnavailable):
        return VisionAuthorizationDecision("blocked", "current_production_model_proof_unavailable")
    if proof.model_record_id != vision.model_record_id:
        return VisionAuthorizationDecision("blocked", "production_model_proof_identity_mismatch")

    capabilities = tuple(sorted(vision.required_capabilities))
    control_fingerprint = question_control_fingerprint(control)
    auth_fingerprint = _authorization_fingerprint(
        tenant_id=tenant_id,
        context=context,
        item_key=item_key,
        control_fingerprint=control_fingerprint,
        proof=proof,
        capabilities=capabilities,
        field_activation_fingerprint=_field_activation_fingerprint(field_activation),
    )

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        existing = await connection.execute(
            text(
                """
                SELECT id, expires_at, consumed_at
                FROM audit_vision_inference_authorizations
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND authorization_fingerprint=:authorization_fingerprint
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "authorization_fingerprint": auth_fingerprint},
        )
        existing_row = existing.mappings().first()
        if existing_row is not None:
            if existing_row["consumed_at"] is not None:
                return VisionAuthorizationDecision(
                    "blocked",
                    "vision_authorization_already_consumed",
                )
            validity = await connection.execute(
                text("SELECT :expires_at > CURRENT_TIMESTAMP AS valid"),
                {"expires_at": existing_row["expires_at"]},
            )
            if not bool(validity.scalar_one()):
                return VisionAuthorizationDecision("blocked", "vision_authorization_expired")
            return VisionAuthorizationDecision(
                status="authorized",
                reason="existing_single_use_authorization",
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
                    INSERT INTO audit_vision_inference_authorizations (
                        tenant_id, audit_run_id, item_key,
                        redaction_receipt_id, privacy_verification_event_id,
                        program_key, program_version, question_control_fingerprint,
                        model_record_id, artifact_sha256, artifact_provenance_fingerprint,
                        production_promotion_fingerprint, production_release_proof_fingerprint,
                        capabilities, authorization_fingerprint, expires_at
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:audit_run_id AS UUID), :item_key,
                        CAST(:redaction_receipt_id AS UUID),
                        CAST(:privacy_verification_event_id AS UUID),
                        :program_key, :program_version, :question_control_fingerprint,
                        :model_record_id, :artifact_sha256, :artifact_provenance_fingerprint,
                        :production_promotion_fingerprint, :production_release_proof_fingerprint,
                        CAST(:capabilities AS JSONB), :authorization_fingerprint,
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
                    "privacy_verification_event_id": str(privacy_verification_event_id),
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
                    "capabilities": json.dumps(list(capabilities), separators=(",", ":")),
                    "authorization_fingerprint": auth_fingerprint,
                },
            )
        except IntegrityError as exc:
            raise AuditConflictError("vision inference authorization collision") from exc
        row = inserted.mappings().one()

    return VisionAuthorizationDecision(
        status="authorized",
        reason="privacy_model_and_field_authorities_passed",
        authorization_id=str(row["id"]),
        authorization_fingerprint=auth_fingerprint,
        expires_at=row["expires_at"],
        model_record_id=proof.model_record_id,
        capabilities=capabilities,
        vision_inference_authorized=True,
    )


async def consume_vision_inference_authorization(
    *,
    tenant_id: str,
    authorization_id: UUID,
    authorization_fingerprint: str,
) -> dict[str, object]:
    """Atomically consume the exact inference lease once, immediately before model execution."""

    if len(authorization_fingerprint) != 64:
        raise AuditRepositoryError("invalid vision authorization fingerprint")
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                UPDATE audit_vision_inference_authorizations authorization
                SET consumed_at=CURRENT_TIMESTAMP
                FROM audit_runs run,
                     audit_redaction_verification_events privacy
                WHERE authorization.tenant_id=CAST(:tenant_id AS UUID)
                  AND authorization.id=CAST(:authorization_id AS UUID)
                  AND authorization.authorization_fingerprint=:authorization_fingerprint
                  AND authorization.consumed_at IS NULL
                  AND authorization.expires_at > CURRENT_TIMESTAMP
                  AND run.tenant_id=authorization.tenant_id
                  AND run.id=authorization.audit_run_id
                  AND run.status <> 'cancelled'
                  AND privacy.tenant_id=authorization.tenant_id
                  AND privacy.id=authorization.privacy_verification_event_id
                  AND privacy.verification_status='verified'
                  AND privacy.verification_authority_version=:privacy_authority_version
                RETURNING authorization.audit_run_id, authorization.item_key,
                          authorization.redaction_receipt_id,
                          authorization.privacy_verification_event_id,
                          authorization.model_record_id,
                          authorization.artifact_sha256,
                          authorization.artifact_provenance_fingerprint,
                          authorization.production_promotion_fingerprint,
                          authorization.production_release_proof_fingerprint,
                          authorization.capabilities,
                          authorization.authorization_fingerprint,
                          authorization.consumed_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "authorization_id": str(authorization_id),
                "authorization_fingerprint": authorization_fingerprint,
                "privacy_authority_version": SERVER_PRIVACY_AUTHORITY_VERSION,
            },
        )
        row = result.mappings().first()
        if row is None:
            raise AuditRepositoryError(
                "vision inference authorization unavailable, expired, or consumed"
            )
        return dict(row)
