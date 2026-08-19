from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.audit.evidence_binding_schemas import AuditEvidenceBindingCreate

ROOT = Path(__file__).resolve().parents[1]


def test_binding_payload_has_no_client_chosen_evidence_ref() -> None:
    payload = AuditEvidenceBindingCreate(
        field_evidence_receipt_id=uuid4(),
        source_fingerprint="a" * 64,
        privacy_policy_version="audit-privacy-v1",
        detector_model_ref="mediapipe-face:test",
    )
    assert not hasattr(payload, "redacted_evidence_ref")

    with pytest.raises(ValidationError):
        AuditEvidenceBindingCreate(
            field_evidence_receipt_id=uuid4(),
            source_fingerprint="a" * 64,
            privacy_policy_version="audit-privacy-v1",
            detector_model_ref="mediapipe-face:test",
            redacted_evidence_ref="client-controlled",
        )


def test_binding_requires_same_run_mission_and_location() -> None:
    source = (ROOT / "app/modules/audit/evidence_binding.py").read_text(encoding="utf-8")
    assert "field_evidence_object_receipts" in source
    assert "field_evidence_receipt_id" in source
    assert "mission_id = CAST(:mission_id AS UUID)" in source
    assert "location_id = :location_id" in source
    assert "run.field_mission_id" in source
    assert "run.location_id" in source


def test_canonical_redacted_reference_is_server_generated() -> None:
    source = (ROOT / "app/modules/audit/evidence_binding.py").read_text(encoding="utf-8")
    assert 'canonical_ref = f"field-evidence-receipt:{field_receipt.id}"' in source
    assert '"redacted_evidence_ref": canonical_ref' in source
    assert '"redacted_object_hash_verified": True' in source
    assert '"source_fingerprint_verified": False' in source
    assert '"server_privacy_verified": False' in source
    assert '"vision_inference_authorized": False' in source


def test_binding_is_idempotent_but_rejects_provenance_rebinding() -> None:
    source = (ROOT / "app/modules/audit/evidence_binding.py").read_text(encoding="utf-8")
    assert "idempotent_replay" in source
    assert "already bound to different source provenance" in source
    assert "existing.source_fingerprint != source_fingerprint" in source


def test_public_redaction_route_uses_binding_payload_and_service() -> None:
    source = (ROOT / "app/modules/audit/routes.py").read_text(encoding="utf-8")
    assert "AuditEvidenceBindingCreate" in source
    assert "bind_server_evidence_to_redaction_receipt" in source
    redaction_segment = source.split('"/runs/{audit_run_id}/redaction-receipts"', 1)[1]
    redaction_segment = redaction_segment.split("@router.post", 1)[0]
    assert "AuditRedactionReceiptCreate" not in redaction_segment
    assert "append_redaction_receipt" not in redaction_segment
    assert "payload.field_evidence_receipt_id" in redaction_segment


def test_field_receipt_columns_are_authoritative_in_existing_upload_service() -> None:
    source = (
        ROOT / "app/modules/field_intelligence/evidence_object_upload.py"
    ).read_text(encoding="utf-8")
    for required in (
        "field_evidence_object_receipts",
        "receipt_id",
        "mission_id",
        "location_id",
        "field_key",
        "media_type",
        "sha256",
        "byte_size",
        "storage_provider",
        "storage_key",
        "client_submission_id",
    ):
        assert required in source
