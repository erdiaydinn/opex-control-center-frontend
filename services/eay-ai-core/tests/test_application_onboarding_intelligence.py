from datetime import datetime, timedelta, timezone

import pytest

from app.api_discovery_intelligence import CaptureSource
from app.application_onboarding import (
    ApplicationEnvironmentKind,
    ApplicationOnboardingSession,
    OnboardingStatus,
    TransportPreference,
    compile_onboarded_read_capability,
    create_read_demonstration,
    discover_read_capability,
)
from app.browser_api_observer import observe_browser_exchange
from app.playwright_computer_runtime import (
    BrowserActionKind,
    BrowserActionReceipt,
    LocatorKind,
)
from app.procedural_memory import ProcedureStatus


NOW = datetime(2026, 8, 18, 7, 20, tzinfo=timezone.utc)
HOST = "portal.example.com"
AUTH = "auth://corporate-session-1"
TENANT = "tenant://SYNTHETIC_A"


def _observation(*, method="GET", path="/api/inventory/stock", action="browser-action:search", auth=AUTH):
    return observe_browser_exchange(
        application_id="synthetic-carsiportal",
        capture_source=CaptureSource.PLAYWRIGHT_NETWORK,
        method=method,
        url=f"https://{HOST}{path}?warehouse=fulya&token=must-be-removed",
        status_code=200,
        allowed_hosts={HOST},
        resource_type="xhr",
        request_headers={"authorization": "Bearer transient-secret"},
        response_headers={"content-type": "application/json", "set-cookie": "secret-cookie"},
        response_content_type="application/json",
        response_payload={"barcode": "8690000000001", "stock": 10},
        user_action_ref=action,
        auth_context_ref=auth,
        tenant_scope_ref=TENANT,
    )


def _receipt(*, session_suffix="1", observation=None, page="/inventory", ignored=0, errors=(), auth=AUTH):
    return BrowserActionReceipt(
        action_id=f"search-{session_suffix}",
        application_id="synthetic-carsiportal",
        tenant_scope_ref=TENANT,
        auth_context_ref=auth,
        locator_kind=LocatorKind.LABEL,
        action_kind=BrowserActionKind.CLICK,
        completed=True,
        page_url_after=f"https://{HOST}{page}",
        observations=(() if observation is None else (observation,)),
        ignored_non_allowlisted_response_count=ignored,
        capture_errors=errors,
    )


def _session(
    session_id="session-1",
    *,
    observed_at=NOW,
    observation=None,
    verified=True,
    business_write=False,
    page="/inventory",
    ignored=0,
    errors=(),
):
    return ApplicationOnboardingSession(
        session_id=session_id,
        application_id="synthetic-carsiportal",
        tenant_scope_ref=TENANT,
        auth_context_ref=AUTH,
        environment_kind=ApplicationEnvironmentKind.SYNTHETIC,
        allowed_hosts=frozenset({HOST}),
        observed_at=observed_at,
        receipts=(
            _receipt(
                session_suffix=session_id,
                observation=observation or _observation(),
                page=page,
                ignored=ignored,
                errors=errors,
            ),
        ),
        evidence_refs=(f"evidence://onboarding/{session_id}",),
        business_write_observed=business_write,
        authoritative_read_verified=verified,
        synthetic_fixture=True,
    )


def test_read_only_observation_builds_secret_safe_profile_and_non_executable_candidate():
    session = _session()
    profile, candidate = discover_read_capability(session=session, capability_name="inventory.read_stock")

    assert profile.environment_kind is ApplicationEnvironmentKind.SYNTHETIC
    assert len(profile.environment_fingerprint) == 64
    assert profile.raw_page_urls_retained is False
    assert profile.raw_secrets_retained is False
    assert profile.auth_context_bound is True
    assert profile.allowed_hosts == (HOST,)
    assert candidate.status is OnboardingStatus.READ_CAPABILITY_CANDIDATE
    assert candidate.transport_preference is TransportPreference.OBSERVED_READ_API
    assert candidate.direct_execution_allowed is False
    assert candidate.write_capability_allowed is False
    assert len(candidate.observed_api_candidates) == 1
    assert candidate.observed_api_candidates[0].method == "GET"
    assert "token=" not in candidate.observed_api_candidates[0].path_template
    serialized = profile.model_dump_json() + candidate.model_dump_json()
    assert "must-be-removed" not in serialized
    assert "transient-secret" not in serialized
    assert "8690000000001" not in serialized


def test_mutating_observed_network_traffic_blocks_read_only_onboarding():
    session = _session(observation=_observation(method="POST", path="/api/inventory/adjust"))
    _, candidate = discover_read_capability(session=session, capability_name="inventory.read_stock")

    assert candidate.status is OnboardingStatus.BLOCKED
    assert "application_onboarding_mutating_traffic_observed" in candidate.blockers
    assert candidate.direct_execution_allowed is False
    with pytest.raises(ValueError, match="blocked_onboarding_candidate_cannot_create_demonstration"):
        create_read_demonstration(session=session, candidate=candidate)


def test_explicit_business_write_or_incomplete_capture_blocks_onboarding():
    business_write = discover_read_capability(session=_session(business_write=True), capability_name="inventory.read_stock")[1]
    capture_error = discover_read_capability(session=_session(errors=("TimeoutError",)), capability_name="inventory.read_stock")[1]
    nonallowlisted = discover_read_capability(session=_session(ignored=1), capability_name="inventory.read_stock")[1]

    assert "application_onboarding_mutating_traffic_observed" in business_write.blockers
    assert "application_onboarding_browser_capture_incomplete" in capture_error.blockers
    assert "application_onboarding_non_allowlisted_traffic_observed" in nonallowlisted.blockers
    assert all(item.status is OnboardingStatus.BLOCKED for item in (business_write, capture_error, nonallowlisted))


def test_one_verified_read_demonstration_remains_candidate_two_independent_reads_validate():
    first_session = _session("session-a", observed_at=NOW)
    second_session = _session("session-b", observed_at=NOW + timedelta(minutes=10))
    _, candidate = discover_read_capability(session=first_session, capability_name="inventory.read_stock")
    first_demo = create_read_demonstration(session=first_session, candidate=candidate)
    second_demo = create_read_demonstration(session=second_session, candidate=candidate)

    one = compile_onboarded_read_capability(candidate=candidate, demonstrations=[first_demo])
    two = compile_onboarded_read_capability(candidate=candidate, demonstrations=[first_demo, second_demo])

    assert one.status is ProcedureStatus.CANDIDATE
    assert one.direct_execution_allowed is False
    assert "procedure_verified_demonstrations_insufficient" in one.blockers
    assert two.status is ProcedureStatus.VALIDATED
    assert two.direct_execution_allowed is True
    assert two.requires_revalidation is False
    assert set(two.demonstrations) == {"onboarding:session-a", "onboarding:session-b"}


def test_unverified_read_cannot_count_as_verified_procedure_evidence():
    session = _session("unverified", verified=False)
    _, candidate = discover_read_capability(session=session, capability_name="inventory.read_stock")
    demo = create_read_demonstration(session=session, candidate=candidate)
    compiled = compile_onboarded_read_capability(
        candidate=candidate,
        demonstrations=[demo, demo.model_copy(update={"demonstration_id": "onboarding:unverified-2"})],
    )

    assert demo.successful is False
    assert demo.effect_verified is False
    assert compiled.status is ProcedureStatus.CANDIDATE
    assert compiled.direct_execution_allowed is False


def test_environment_drift_changes_fingerprint_and_rejects_old_candidate_binding():
    original = _session("original", page="/inventory")
    drifted = _session("drifted", page="/inventory-v2")
    original_profile, candidate = discover_read_capability(session=original, capability_name="inventory.read_stock")
    drifted_profile, _ = discover_read_capability(session=drifted, capability_name="inventory.read_stock")

    assert original_profile.environment_fingerprint != drifted_profile.environment_fingerprint
    with pytest.raises(ValueError, match="onboarding_candidate_environment_mismatch"):
        create_read_demonstration(session=drifted, candidate=candidate)


def test_synthetic_environment_must_be_explicitly_fixture_labeled():
    with pytest.raises(ValueError, match="synthetic_onboarding_environment_requires_fixture_label"):
        ApplicationOnboardingSession(
            session_id="bad",
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref=AUTH,
            environment_kind=ApplicationEnvironmentKind.SYNTHETIC,
            allowed_hosts=frozenset({HOST}),
            observed_at=NOW,
            receipts=(_receipt(),),
            evidence_refs=("evidence://bad",),
            synthetic_fixture=False,
        )


def test_receipt_application_tenant_and_auth_identity_mismatch_fail_closed():
    wrong_app = _receipt().model_copy(update={"application_id": "other-app"})
    with pytest.raises(ValueError, match="application_onboarding_receipt_application_mismatch"):
        ApplicationOnboardingSession(
            session_id="wrong-app",
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref=AUTH,
            environment_kind=ApplicationEnvironmentKind.SYNTHETIC,
            allowed_hosts=frozenset({HOST}),
            observed_at=NOW,
            receipts=(wrong_app,),
            evidence_refs=("evidence://wrong-app",),
            synthetic_fixture=True,
        )

    wrong_tenant = _receipt().model_copy(update={"tenant_scope_ref": "tenant://SYNTHETIC_B"})
    with pytest.raises(ValueError, match="application_onboarding_receipt_tenant_mismatch"):
        ApplicationOnboardingSession(
            session_id="wrong-tenant",
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref=AUTH,
            environment_kind=ApplicationEnvironmentKind.SYNTHETIC,
            allowed_hosts=frozenset({HOST}),
            observed_at=NOW,
            receipts=(wrong_tenant,),
            evidence_refs=("evidence://wrong-tenant",),
            synthetic_fixture=True,
        )

    wrong_auth = _receipt(auth="auth://other-session")
    with pytest.raises(ValueError, match="application_onboarding_receipt_auth_context_mismatch"):
        ApplicationOnboardingSession(
            session_id="wrong-auth",
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref=AUTH,
            environment_kind=ApplicationEnvironmentKind.SYNTHETIC,
            allowed_hosts=frozenset({HOST}),
            observed_at=NOW,
            receipts=(wrong_auth,),
            evidence_refs=("evidence://wrong-auth",),
            synthetic_fixture=True,
        )


def test_observation_auth_context_mismatch_fails_closed_even_when_receipt_matches():
    receipt = _receipt(observation=_observation(auth="auth://other-session"))
    with pytest.raises(ValueError, match="application_onboarding_observation_auth_context_mismatch"):
        ApplicationOnboardingSession(
            session_id="wrong-observation-auth",
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref=AUTH,
            environment_kind=ApplicationEnvironmentKind.SYNTHETIC,
            allowed_hosts=frozenset({HOST}),
            observed_at=NOW,
            receipts=(receipt,),
            evidence_refs=("evidence://wrong-observation-auth",),
            synthetic_fixture=True,
        )
