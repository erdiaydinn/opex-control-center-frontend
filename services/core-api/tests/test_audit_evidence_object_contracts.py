from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _evidence_route_source() -> str:
    return (
        ROOT / "app/modules/audit/evidence_object_routes.py"
    ).read_text(encoding="utf-8")


def test_audit_evidence_adapter_derives_authority_from_run() -> None:
    source = _evidence_route_source()
    assert "ar.field_mission_id" in source
    assert "ar.location_id" in source
    assert "get_run_location" in source
    assert "authority.get(\"field_mission_id\")" in source
    assert "location_id = str(scoped_location.get(\"location_id\")" in source


def test_audit_evidence_adapter_reuses_private_field_store_authority() -> None:
    source = _evidence_route_source()
    assert "upload_private_evidence_object" in source
    assert "MAX_EVIDENCE_BYTES" in source
    assert "expected_sha256=content_sha256" in source
    assert "mission_id=str(mission_id)" in source
    assert "location_id=location_id" in source


def test_missing_governed_field_mission_fails_closed() -> None:
    source = _evidence_route_source()
    assert "if mission_id is None:" in source
    assert "Audit run has no governed Field mission for private evidence storage" in source
    assert "status_code=status.HTTP_409_CONFLICT" in source


def test_server_storage_receipt_never_becomes_privacy_or_vision_authority() -> None:
    source = _evidence_route_source()
    assert '"authority": "server_issued_private_evidence_receipt"' in source
    assert '"client_redaction_claim_only": True' in source
    assert '"server_privacy_verified": False' in source
    assert '"vision_inference_authorized": False' in source
    assert '"public_url": None' in source
    assert '"production_storage_evidence": False' in source


def test_evidence_adapter_uses_canonical_scope_and_hash_boundaries() -> None:
    source = _evidence_route_source()
    assert "scope_allows_location" in source
    assert 'require_audit_scope(principal, "action:audit:submitEvidence")' in source
    assert 'Header(alias="X-EAY-Content-SHA256")' in source
    assert "_valid_sha256(content_sha256)" in source
    assert ".allows(" not in source


def test_audit_evidence_router_is_composed_into_platform_asgi() -> None:
    source = (ROOT / "app/budget_main.py").read_text(encoding="utf-8")
    assert "audit_evidence_object_router" in source
    assert "app.include_router(audit_evidence_object_router)" in source
