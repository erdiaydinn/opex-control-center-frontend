from datetime import datetime, timezone

import pytest

from app.browser_harness_router import BrowserHarness
from app.enterprise_browser_onboarding import (
    AuthenticatedBrowserSessionEvidence,
    prepare_enterprise_read_onboarding_runtime,
)


NOW = datetime(2026, 8, 18, 8, 25, tzinfo=timezone.utc)
APP = "yemeksepeti-carsi-portal"
HOST = "carsi-portal.yemeksepeti.com"


def _session(**overrides):
    payload = dict(
        application_id=APP,
        tenant_scope_ref="tenant://YS_TR",
        auth_context_ref="auth://okta/carsi/session-1",
        identity_evidence_ref="identity://okta/carsi/user-verified",
        observed_at=NOW,
        observed_url=f"https://{HOST}/tr/?warehouse=fulya&token=transient",
        authenticated=True,
        network_egress_boundary_ref="egress://managed-corporate-browser/ys-tr",
    )
    payload.update(overrides)
    return AuthenticatedBrowserSessionEvidence(**payload)


def test_real_carsiportal_identity_composes_playwright_primary_and_agent_browser_secondary():
    runtime = prepare_enterprise_read_onboarding_runtime(
        application_id=APP,
        session=_session(),
        agent_browser_available=True,
        agent_browser_session_name="eay-carsi-read",
    )

    assert runtime.application_id == APP
    assert runtime.observed_origin_shape == f"https://{HOST}/tr/"
    assert runtime.playwright.allowed_hosts == frozenset({HOST})
    assert runtime.playwright.auth_context_ref == "auth://okta/carsi/session-1"
    assert runtime.harness_route.primary is BrowserHarness.PLAYWRIGHT
    assert runtime.harness_route.secondary == (BrowserHarness.AGENT_BROWSER,)
    assert runtime.agent_browser is not None
    assert runtime.agent_browser.allowed_hosts == frozenset({HOST})
    assert runtime.agent_browser.session_name == "eay-carsi-read"
    assert runtime.read_only is True
    assert runtime.write_execution_allowed is False
    assert runtime.direct_api_execution_allowed is False
    assert runtime.application_field_production_verified is False
    serialized = runtime.model_dump_json()
    assert "warehouse=fulya" not in serialized
    assert "token=transient" not in serialized


def test_agent_browser_is_omitted_without_egress_boundary_even_if_binary_is_available():
    runtime = prepare_enterprise_read_onboarding_runtime(
        application_id=APP,
        session=_session(network_egress_boundary_ref=None),
        agent_browser_available=True,
    )
    assert runtime.harness_route.primary is BrowserHarness.PLAYWRIGHT
    assert runtime.harness_route.secondary == ()
    assert runtime.agent_browser is None


def test_wrong_host_or_application_cannot_bind_to_registered_carsiportal_identity():
    with pytest.raises(ValueError, match="enterprise_browser_session_host_not_registered"):
        prepare_enterprise_read_onboarding_runtime(
            application_id=APP,
            session=_session(observed_url="https://evil.example.net/tr/"),
        )

    with pytest.raises(ValueError, match="enterprise_browser_session_application_mismatch"):
        prepare_enterprise_read_onboarding_runtime(
            application_id=APP,
            session=_session(application_id="other-app"),
        )


def test_unauthenticated_session_never_reaches_portal_onboarding():
    with pytest.raises(ValueError, match="enterprise_browser_onboarding_requires_authenticated_session"):
        _session(authenticated=False)


def test_raw_observed_url_is_excluded_from_session_evidence_serialization():
    session = _session()
    serialized = session.model_dump_json()
    assert "warehouse=fulya" not in serialized
    assert "token=transient" not in serialized
    assert session.observed_url.endswith("token=transient")
