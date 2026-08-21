from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.modules.audit.control_contracts import (
    AuditQuestionControl,
    AuditVisionContract,
    question_control_fingerprint,
)
from app.modules.audit.video_verification_runtime import (
    AuditCanonicalVideoFrame,
    AuditCanonicalVideoManifest,
    AuditDecodedVideo,
    AuditDecodedVideoFrame,
    _manifest_fingerprint,
)
from app.modules.audit.video_verification_service import (
    VIDEO_VERIFICATION_AUTHORITY_VERSION,
    _verification_fingerprint,
)
from app.modules.audit.video_vision_authorization import (
    _authorization_fingerprint,
    _video_event_is_current_and_intact,
)
from app.modules.audit.vision_model_proof import ProductionModelProof
from app.modules.field_intelligence.evidence_object_upload import (
    FieldEvidenceStoreUnavailable,
)
from app.modules.field_intelligence.video_object_read import read_private_video_object

CORE_API_ROOT = Path(__file__).resolve().parents[1]
TENANT_ID = str(uuid4())
RECEIPT_ID = str(uuid4())
BASE_URL = "https://field-evidence-store"
TRUSTED = frozenset({"field-evidence-store"})


@pytest.mark.asyncio
async def test_private_video_reader_returns_exact_mp4_bytes_without_redirects() -> None:
    body = b"governed-private-mp4"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/private/field-evidence/{RECEIPT_ID}"
        assert request.headers["x-eay-field-tenant"] == TENANT_ID
        assert request.headers["x-eay-field-expected-bytes"] == str(len(body))
        assert request.headers["accept"] == "video/mp4"
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4", "content-length": str(len(body))},
            content=body,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await read_private_video_object(
            tenant_id=TENANT_ID,
            receipt_id=RECEIPT_ID,
            expected_byte_size=len(body),
            client=client,
            base_url=BASE_URL,
            trusted_hosts=TRUSTED,
            token="opaque-test-token",
        )
    assert result == body


@pytest.mark.asyncio
async def test_private_video_reader_rejects_non_mp4_object() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg", "content-length": "4"},
            content=b"four",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FieldEvidenceStoreUnavailable, match="non-video/mp4"):
            await read_private_video_object(
                tenant_id=TENANT_ID,
                receipt_id=RECEIPT_ID,
                expected_byte_size=4,
                client=client,
                base_url=BASE_URL,
                trusted_hosts=TRUSTED,
            )


@pytest.mark.asyncio
async def test_private_video_reader_rejects_untrusted_gateway_host() -> None:
    with pytest.raises(FieldEvidenceStoreUnavailable, match="configuration is invalid"):
        await read_private_video_object(
            tenant_id=TENANT_ID,
            receipt_id=RECEIPT_ID,
            expected_byte_size=4,
            base_url="https://evil.example",
            trusted_hosts=TRUSTED,
        )


def _verified_video_context() -> dict[str, object]:
    tenant_id = str(uuid4())
    run_id = uuid4()
    redaction_id = uuid4()
    verification_id = uuid4()
    source = b"immutable-private-mp4"
    source_sha = hashlib.sha256(source).hexdigest()
    jpeg = b"canonical-jpeg-frame"
    frame = AuditCanonicalVideoFrame(
        sequence=0,
        timestamp_ms=0,
        sha256=hashlib.sha256(jpeg).hexdigest(),
        byte_size=len(jpeg),
        privacy_verification_fingerprint="b" * 64,
    )
    decoded = AuditDecodedVideo(
        frames=(AuditDecodedVideoFrame(sequence=0, timestamp_ms=0, jpeg_bytes=jpeg),),
        duration_ms=1_000,
        decoder_ref="server-decoder:v1",
        decoder_fingerprint="c" * 64,
    )
    manifest_fingerprint = _manifest_fingerprint(
        source_sha256=source_sha,
        source_byte_size=len(source),
        decoded=decoded,
        frames=(frame,),
    )
    manifest = AuditCanonicalVideoManifest(
        status="verified",
        reason="canonical frame privacy verification passed",
        source_sha256=source_sha,
        source_byte_size=len(source),
        duration_ms=decoded.duration_ms,
        canonical_frame_count=1,
        processed_frame_count=1,
        decoder_ref=decoded.decoder_ref,
        decoder_fingerprint=decoded.decoder_fingerprint,
        frames=(frame,),
        manifest_fingerprint=manifest_fingerprint,
        privacy_gate_passed=True,
    )
    verification_fingerprint = _verification_fingerprint(
        tenant_id=tenant_id,
        audit_run_id=run_id,
        redaction_receipt_id=redaction_id,
        manifest=manifest,
    )
    return {
        "tenant_id": tenant_id,
        "audit_run_id": run_id,
        "redaction_receipt_id": redaction_id,
        "video_verification_event_id": verification_id,
        "verification_status": "verified",
        "verification_authority_version": VIDEO_VERIFICATION_AUTHORITY_VERSION,
        "verification_fingerprint": verification_fingerprint,
        "verification_reason": manifest.reason,
        "media_kind": "video",
        "redacted_object_sha256": source_sha,
        "redacted_object_byte_size": len(source),
        "observed_sha256": source_sha,
        "observed_byte_size": len(source),
        "decoder_ref": decoded.decoder_ref,
        "decoder_fingerprint": decoded.decoder_fingerprint,
        "duration_ms": decoded.duration_ms,
        "canonical_frame_count": 1,
        "processed_frame_count": 1,
        "manifest_fingerprint": manifest_fingerprint,
        "frame_manifest": [
            {
                "sequence": frame.sequence,
                "timestamp_ms": frame.timestamp_ms,
                "sha256": frame.sha256,
                "byte_size": frame.byte_size,
                "privacy_verification_fingerprint": frame.privacy_verification_fingerprint,
            }
        ],
        "program_key": "market.audit.v1",
        "program_version": 1,
    }


def test_only_exact_persisted_video_event_is_accepted() -> None:
    context = _verified_video_context()
    assert _video_event_is_current_and_intact(context) is True

    tampered_manifest = dict(context)
    tampered_manifest["manifest_fingerprint"] = "d" * 64
    assert _video_event_is_current_and_intact(tampered_manifest) is False

    wrong_decoder = dict(context)
    wrong_decoder["decoder_fingerprint"] = "e" * 64
    assert _video_event_is_current_and_intact(wrong_decoder) is False

    image_event = dict(context)
    image_event["media_kind"] = "image"
    assert _video_event_is_current_and_intact(image_event) is False


def test_video_authorization_fingerprint_binds_manifest_decoder_model_and_tenant() -> None:
    context = _verified_video_context()
    control = AuditQuestionControl(
        item_key="cold_room_video_condition",
        evidence_modalities=("VIDEO",),
        vision_contract=AuditVisionContract(
            model_record_id="video-vision-model",
            required_capabilities=("object_detection", "visual_reasoning"),
        ),
    )
    proof = ProductionModelProof(
        model_record_id="video-vision-model",
        artifact_sha256="1" * 64,
        artifact_provenance_fingerprint="2" * 64,
        production_promotion_fingerprint="3" * 64,
        production_release_proof_fingerprint="4" * 64,
    )
    fingerprint = _authorization_fingerprint(
        tenant_id=str(context["tenant_id"]),
        context=context,
        item_key=control.item_key,
        control_fingerprint=question_control_fingerprint(control),
        proof=proof,
        capabilities=tuple(sorted(control.vision_contract.required_capabilities)),
        field_activation_fingerprint="5" * 64,
    )
    changed = dict(context)
    changed["manifest_fingerprint"] = "6" * 64
    changed_fingerprint = _authorization_fingerprint(
        tenant_id=str(context["tenant_id"]),
        context=changed,
        item_key=control.item_key,
        control_fingerprint=question_control_fingerprint(control),
        proof=proof,
        capabilities=tuple(sorted(control.vision_contract.required_capabilities)),
        field_activation_fingerprint="5" * 64,
    )
    assert len(fingerprint) == 64
    assert fingerprint != changed_fingerprint

    wrong_tenant = _authorization_fingerprint(
        tenant_id=str(uuid4()),
        context=context,
        item_key=control.item_key,
        control_fingerprint=question_control_fingerprint(control),
        proof=proof,
        capabilities=tuple(sorted(control.vision_contract.required_capabilities)),
        field_activation_fingerprint="5" * 64,
    )
    assert fingerprint != wrong_tenant


def test_video_authority_is_production_composed_and_cannot_assert_a_finding() -> None:
    root = CORE_API_ROOT / "app/modules/audit"
    binding = (root / "evidence_binding.py").read_text(encoding="utf-8")
    service = (root / "video_verification_service.py").read_text(encoding="utf-8")
    authorization = (root / "video_vision_authorization.py").read_text(encoding="utf-8")
    routes = (root / "video_routes.py").read_text(encoding="utf-8")
    composition = (CORE_API_ROOT / "app/budget_main.py").read_text(encoding="utf-8")

    assert '"video/mp4": ("video", 0, 0)' in binding
    assert "read_private_video_object" in service
    assert "ON CONFLICT (tenant_id, verification_fingerprint) DO NOTHING" in service
    assert 'capability="video_vision"' in authorization
    assert "video_decoder_fingerprint" in authorization
    assert '"finding_authorized": False' in authorization
    assert '"action_authorized": False' in authorization
    assert "authorization.consumed_at IS NULL" in authorization
    assert "authorization.expires_at > CURRENT_TIMESTAMP" in authorization
    assert 'getattr(request.app.state, "audit_video_decoder", None)' in routes
    assert 'getattr(request.app.state, "audit_privacy_scanner", None)' in routes
    assert "AuditVideoVisionAuthorizationCreate" in routes
    authorization_create_contract = routes.split(
        "class AuditVideoVisionAuthorizationCreate", 1
    )[1].split("class AuditVideoVisionAuthorizationConsume", 1)[0]
    assert "model_record_id" not in authorization_create_contract
    assert "app.include_router(audit_video_router)" in composition


def test_video_authority_migrations_are_rls_append_only_and_replay_fenced() -> None:
    migration = (
        CORE_API_ROOT / "alembic/versions/0057_audit_video_authority.py"
    ).read_text(encoding="utf-8")
    replay = (
        CORE_API_ROOT / "alembic/versions/0058_audit_video_replay_fence.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0057_audit_video_authority"' in migration
    assert 'down_revision: str = "0056_audit_visit_manifests"' in migration
    assert '"audit_video_verification_events"' in migration
    assert '"audit_video_inference_authorizations"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "prevent_audit_append_only_mutation()" in migration
    assert 'revision: str = "0058_audit_video_replay_fence"' in replay
    assert 'down_revision: str = "0057_audit_video_authority"' in replay
    assert '"uq_audit_video_verification_fingerprint"' in replay
