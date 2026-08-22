from datetime import datetime, timezone

import pytest

from app.api_discovery_intelligence import CaptureSource
from app.application_onboarding import (
    ApplicationEnvironmentKind,
    ApplicationOnboardingSession,
    create_read_demonstration,
    discover_read_capability,
)
from app.browser_api_observer import observe_browser_exchange
from app.playwright_computer_runtime import BrowserActionKind, BrowserActionReceipt, LocatorKind
from app.playwright_mission_adapter import BrowserEffectVerification, EffectVerificationStatus


NOW = datetime(2026, 8, 18, 8, 55, tzinfo=timezone.utc)
HOST = "portal.example.com"
APP = "corporate-portal"
TENANT = "tenant://YS_TR"
AUTH = "auth://corporate-session"
VERIFY_REF = "authoritative-readback://inventory/stock/fulya"


def _observation():
    return observe_browser_exchange(
        application_id=APP,
        capture_source=CaptureSource.PLAYWRIGHT_NETWORK,
        method="GET",
        url=f"https://{HOST}/api/inventory/stock?warehouse=fulya",
        status_code=200,
        allowed_hosts={HOST},
        resource_type="xhr",
        request_headers={"authorization": "Bearer transient"},
        response_headers={"content-type": "application/json"},
        response_content_type="application/json",
        response_payload={"stock": 10},
        user_action_ref="browser-action:read-stock",
        auth_context_ref=AUTH,
        tenant_scope_ref=TENANT,
    )


def _receipt():
    return BrowserActionReceipt(
        action_id="read-stock",
        application_id=APP,
        tenant_scope_ref=TENANT,
        auth_context_ref=AUTH,
        locator_kind=LocatorKind.LABEL,
        action_kind=BrowserActionKind.CLICK,
        completed=True,
        page_url_after=f"https://{HOST}/inventory",
        observations=(_observation(),),
    )


def _session(*, verification=None, legacy_verified=False, evidence_refs=(VERIFY_REF,)):
    return ApplicationOnboardingSession(
        session_id="production-read-1",
        application_id=APP,
        tenant_scope_ref=TENANT,
        auth_context_ref=AUTH,
        environment_kind=ApplicationEnvironmentKind.PRODUCTION,
        allowed_hosts=frozenset({HOST}),
        observed_at=NOW,
        receipts=(_receipt(),),
        evidence_refs=evidence_refs,
        authoritative_read_verified=legacy_verified,
        authoritative_read_verification=verification,
    )


def test_production_client_boolean_cannot_claim_authoritative_read():
    with pytest.raises(ValueError, match="non_synthetic_read_verification_requires_verifier_receipt"):
        _session(legacy_verified=True, verification=None)


def test_production_unknown_verifier_cannot_create_verified_read_evidence():
    verification = BrowserEffectVerification(
        status=EffectVerificationStatus.UNKNOWN,
        evidence_refs=(VERIFY_REF,),
        error_code="readback_timeout",
    )
    with pytest.raises(ValueError, match="non_synthetic_read_verifier_must_confirm_authoritative_read"):
        _session(verification=verification)


def test_production_verifier_evidence_must_be_in_session_bundle():
    verification = BrowserEffectVerification(
        status=EffectVerificationStatus.VERIFIED_APPLIED,
        evidence_refs=(VERIFY_REF,),
    )
    with pytest.raises(ValueError, match="read_verifier_evidence_must_be_bound_to_onboarding_session"):
        _session(verification=verification, evidence_refs=("evidence://different-readback",))


def test_evidence_bound_production_verifier_creates_verified_read_demonstration():
    verification = BrowserEffectVerification(
        status=EffectVerificationStatus.VERIFIED_APPLIED,
        evidence_refs=(VERIFY_REF,),
    )
    session = _session(verification=verification)
    _, candidate = discover_read_capability(
        session=session,
        capability_name="inventory.read_stock",
    )
    demonstration = create_read_demonstration(session=session, candidate=candidate)

    assert demonstration.successful is True
    assert demonstration.effect_verified is True
    assert VERIFY_REF in demonstration.evidence_refs
