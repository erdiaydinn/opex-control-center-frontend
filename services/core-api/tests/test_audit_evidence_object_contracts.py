from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_audit_evidence_adapter_derives_mission_and_location_from_run() -> None:
    source = (
        ROOT / "app/modules/audit/evidence_object_routes.py"
    ).read_text(encoding="utf-8")
    assert "ar.field_mission_id" in source
    assert "ar.location_id" in source
    assert "get_run_location" in source
    assert "mission_id: UUID" not in source
    assert "location_id: str," not in source.split("async def post_audit_evidence_object", 1)[1].split(") ->", 1)[0]


def test_audit_evidence_adapter_reuses_private_field_store_authority() -> None:
    source = (
        ROOT / "app/modules/audit/evidence_object_routes.py"
    ).read_text(encoding="utf-8")
    assert "upload_private_evidence_object" in source
    assert 'media_type=request.headers.get("content-type", "")' in source
    assert "expected_sha256=content_sha256" in source
    assert "MAX_EVIDENCE_BYTES" in source


def test_audit_evidence_requires_active_governed_field_mission() -> None:
    source = (
        ROOT / "app/modules/audit/evidence_object_routes.py"
    ).read_text(encoding="utf-8")
    assert "Audit run has no governed Field mission for private evidence storage" in source
    field_store = (
        ROOT / "app/modules/field_intelligence/evidence_object_upload.py"
    ).read_text(encoding="utf-8")
    assert "mission.status='active'" in field_store
    assert "target.status NOT IN ('verified','exempt')" in field_store
    assert "field->>'type'='photo'" in field_store


def test_server_receipt_does_not_authorize_vision_from_client_redaction_claim() -> None:
    source = (
        ROOT / "app/modules/audit/evidence_object_routes.py"
    ).read_text(encoding="utf-8")
    assert '"authority": "server_issued_private_evidence_receipt"' in source
    assert '"client_redaction_claim_only": True' in source
    assert '"server_privacy_verified": False' in source
    assert '"vision_inference_authorized": False' in source
    assert '"public_url": None' in source


def test_evidence_adapter_uses_canonical_audit_scope_helper() -> None:
    source = (
        ROOT / "app/modules/audit/evidence_object_routes.py"
    ).read_text(encoding="utf-8")
    assert "scope_allows_location" in source
    assert ".allows(" not in source
    assert 'require_audit_scope(principal, "action:audit:submitEvidence")' in source


def test_audit_evidence_router_is_composed_into_platform_asgi() -> None:
    source = (ROOT / "app/budget_main.py").read_text(encoding="utf-8")
    assert "audit_evidence_object_router" in source
    assert "app.include_router(audit_evidence_object_router)" in source
