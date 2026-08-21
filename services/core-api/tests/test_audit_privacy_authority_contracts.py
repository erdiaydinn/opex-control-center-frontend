from pathlib import Path
from uuid import uuid4

from app.modules.audit.privacy_verification_runtime import AuditServerPrivacyVerification
from app.modules.audit.privacy_verification_service import (
    SERVER_PRIVACY_AUTHORITY_VERSION,
    SERVER_PRIVACY_VERIFIER_REF,
    _fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]


def test_privacy_event_fingerprint_is_deterministic_and_authority_version_bound() -> None:
    tenant_id = str(uuid4())
    run_id = uuid4()
    redaction_id = uuid4()
    field_id = uuid4()
    result = AuditServerPrivacyVerification(
        status="blocked",
        reason="private evidence content is unavailable",
        observed_sha256="a" * 64,
        observed_byte_size=0,
        scan=None,
        privacy_gate_passed=False,
    )
    first = _fingerprint(
        tenant_id=tenant_id,
        audit_run_id=run_id,
        redaction_receipt_id=redaction_id,
        field_evidence_receipt_id=field_id,
        expected_sha256="b" * 64,
        expected_byte_size=10,
        result=result,
    )
    second = _fingerprint(
        tenant_id=tenant_id,
        audit_run_id=run_id,
        redaction_receipt_id=redaction_id,
        field_evidence_receipt_id=field_id,
        expected_sha256="b" * 64,
        expected_byte_size=10,
        result=result,
    )
    assert first == second
    assert len(first) == 64
    assert SERVER_PRIVACY_AUTHORITY_VERSION == "server_privacy_v2"
    assert SERVER_PRIVACY_VERIFIER_REF == "eay.audit.server_privacy.v1"


def test_server_privacy_service_revalidates_binding_after_network_boundary() -> None:
    source = (ROOT / "app/modules/audit/privacy_verification_service.py").read_text(
        encoding="utf-8"
    )
    assert source.count("await _load_bound_receipt(") >= 2
    assert "field.expires_at > CURRENT_TIMESTAMP" in source
    assert 'bound["storage_provider"] != "private_gateway"' in source
    assert 'bound["redacted_object_sha256"] != bound["field_sha256"]' in source
    assert 'bound["redacted_object_byte_size"] != bound["field_byte_size"]' in source
    assert "except FieldEvidenceStoreUnavailable" in source
    assert 'content = b""' in source


def test_server_privacy_event_is_append_only_authority_not_vision_authority() -> None:
    source = (ROOT / "app/modules/audit/privacy_verification_service.py").read_text(
        encoding="utf-8"
    )
    assert "INSERT INTO audit_redaction_verification_events" in source
    assert "verification_authority_version" in source
    assert "observed_sha256" in source
    assert "observed_byte_size" in source
    assert "scanner_model_fingerprint" in source
    assert '"vision_inference_authorized": False' in source
    assert '"privacy_gate_passed": verification.privacy_gate_passed' in source


def test_privacy_migration_preserves_legacy_events_without_elevating_them() -> None:
    source = (
        ROOT / "alembic/versions/0051_audit_server_privacy_authority.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str = "0050_audit_evidence_binding_integrity"' in source
    assert "verification_authority_version" in source
    assert "server_privacy_v2" in source
    assert "verification_status IN ('verified','rejected','blocked','tampered')" in source
    assert "verification_authority_version IS NULL" in source
    assert "ck_audit_privacy_server_authority_complete" in source
    assert "ck_audit_privacy_verified_has_scanner" in source
    assert "ck_audit_privacy_rejected_has_scanner" in source


def test_private_reader_never_accepts_public_redirect_or_unbound_media_authority() -> None:
    source = (
        ROOT / "app/modules/field_intelligence/evidence_object_read.py"
    ).read_text(encoding="utf-8")
    assert '"GET"' in source
    assert "follow_redirects=False" in source
    assert '"X-EAY-Field-Tenant"' in source
    assert '"X-EAY-Field-Expected-Bytes"' in source
    assert "ALLOWED_MEDIA_TYPES" in source
    assert "normalized_media_type not in ALLOWED_MEDIA_TYPES" in source
    assert '"Accept": normalized_media_type' in source
    assert "media_type != normalized_media_type" in source
    assert "parsed_length != expected_byte_size" in source
    assert "return await _bounded_content" in source
    assert "public_url" not in source
