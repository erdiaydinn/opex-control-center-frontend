from app.browser_harness_router import (
    BrowserHarness,
    BrowserHarnessRequest,
    BrowserMissionKind,
    route_browser_harness,
)


BASE = dict(
    application_id="yemeksepeti-carsi-portal",
    tenant_scope_ref="tenant://YS_TR",
    existing_managed_session=True,
    live_session_identity_bound=True,
    playwright_available=True,
    agent_browser_available=True,
    agent_browser_pin_tab=True,
    network_egress_boundary_ref="egress://managed-corporate-browser/ys-tr",
)


def _request(kind, **overrides):
    payload = dict(BASE)
    payload.update(mission_kind=kind)
    payload.update(overrides)
    return BrowserHarnessRequest(**payload)


def test_network_discovery_is_playwright_only():
    route = route_browser_harness(_request(BrowserMissionKind.NETWORK_API_DISCOVERY))
    assert route.allowed is True
    assert route.primary is BrowserHarness.PLAYWRIGHT
    assert route.secondary == ()
    assert route.network_observation_required is True
    assert route.mutation_allowed is False


def test_read_onboarding_uses_playwright_primary_and_agent_browser_as_safe_secondary():
    route = route_browser_harness(_request(BrowserMissionKind.READ_ONBOARDING))
    assert route.allowed is True
    assert route.primary is BrowserHarness.PLAYWRIGHT
    assert route.secondary == (BrowserHarness.AGENT_BROWSER,)
    assert route.network_observation_required is True


def test_semantic_read_can_prefer_agent_browser_only_when_pinned_identity_and_egress_are_bound():
    route = route_browser_harness(_request(BrowserMissionKind.SEMANTIC_READ))
    assert route.primary is BrowserHarness.AGENT_BROWSER
    assert route.secondary == (BrowserHarness.PLAYWRIGHT,)

    no_egress = route_browser_harness(
        _request(BrowserMissionKind.SEMANTIC_READ, network_egress_boundary_ref=None)
    )
    assert no_egress.primary is BrowserHarness.PLAYWRIGHT
    assert BrowserHarness.AGENT_BROWSER not in no_egress.secondary

    unpinned = route_browser_harness(
        _request(BrowserMissionKind.SEMANTIC_READ, agent_browser_pin_tab=False)
    )
    assert unpinned.primary is BrowserHarness.PLAYWRIGHT

    unverified_session = route_browser_harness(
        _request(BrowserMissionKind.SEMANTIC_READ, live_session_identity_bound=False)
    )
    assert unverified_session.primary is BrowserHarness.PLAYWRIGHT


def test_write_execution_never_routes_to_agent_browser_and_requires_qualification_and_verifier():
    blocked = route_browser_harness(_request(BrowserMissionKind.WRITE_EXECUTION))
    assert blocked.allowed is False
    assert "browser_write_capability_not_qualified" in blocked.blockers
    assert "browser_write_effect_verifier_missing" in blocked.blockers
    assert blocked.mutation_allowed is False

    allowed = route_browser_harness(
        _request(
            BrowserMissionKind.WRITE_EXECUTION,
            mutation_capability_qualified=True,
            effect_verifier_ref="verifier://inventory/authoritative-readback",
        )
    )
    assert allowed.allowed is True
    assert allowed.primary is BrowserHarness.PLAYWRIGHT
    assert allowed.secondary == ()
    assert allowed.mutation_allowed is True
    assert allowed.authoritative_effect_verification_required is True


def test_write_route_fails_closed_without_identity_bound_managed_session():
    route = route_browser_harness(
        _request(
            BrowserMissionKind.WRITE_EXECUTION,
            existing_managed_session=False,
            live_session_identity_bound=False,
            mutation_capability_qualified=True,
            effect_verifier_ref="verifier://inventory/authoritative-readback",
        )
    )
    assert route.allowed is False
    assert "browser_write_managed_session_missing" in route.blockers
    assert "browser_write_session_identity_unverified" in route.blockers


def test_authoritative_state_verification_never_uses_agent_browser_as_primary():
    route = route_browser_harness(_request(BrowserMissionKind.AUTHORITATIVE_STATE_VERIFICATION))
    assert route.allowed is True
    assert route.primary is BrowserHarness.PLAYWRIGHT
    assert route.authoritative_effect_verification_required is True
