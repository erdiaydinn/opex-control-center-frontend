from inspect import signature
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.modules.audit.privacy_routes import (
    _server_privacy_scanner,
    post_server_privacy_verification,
)

ROOT = Path(__file__).resolve().parents[1]


class _Scanner:
    def scan_jpeg(self, content: bytes) -> object:
        return object()


def _request_with(scanner: object | None) -> SimpleNamespace:
    state = SimpleNamespace(audit_privacy_scanner=scanner)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_server_privacy_scanner_is_server_owned_and_fail_closed() -> None:
    scanner = _Scanner()
    assert _server_privacy_scanner(_request_with(scanner)) is scanner

    with pytest.raises(HTTPException) as missing:
        _server_privacy_scanner(_request_with(None))
    assert missing.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    with pytest.raises(HTTPException) as invalid:
        _server_privacy_scanner(_request_with(object()))
    assert invalid.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_public_privacy_trigger_cannot_supply_authority_fields() -> None:
    parameters = set(signature(post_server_privacy_verification).parameters)
    assert parameters == {
        "audit_run_id",
        "redaction_receipt_id",
        "request",
        "principal",
    }
    forbidden = {
        "privacy_gate_passed",
        "server_privacy_verified",
        "verification_status",
        "scanner_model_ref",
        "scanner_model_fingerprint",
        "vision_inference_authorized",
    }
    assert not parameters.intersection(forbidden)


def test_privacy_route_remains_scope_bound_and_server_derived() -> None:
    source = (ROOT / "app/modules/audit/privacy_routes.py").read_text(encoding="utf-8")
    assert "action:audit:submitEvidence" in source
    assert "scope_allows_location" in source
    assert "verify_bound_redaction_receipt" in source
    assert 'getattr(request.app.state, "audit_privacy_scanner", None)' in source
    assert "vision_inference_authorized" not in source


def test_privacy_route_is_composed_into_production_core_app() -> None:
    source = (ROOT / "app/budget_main.py").read_text(encoding="utf-8")
    assert "app.modules.audit.privacy_routes" in source
    assert "app.include_router(audit_privacy_router)" in source
