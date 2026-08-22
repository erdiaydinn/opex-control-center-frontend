import pytest

from app.api_discovery_intelligence import (
    CaptureSource,
    ObservedHttpExchange,
    OperationKind,
    discover_api_candidates,
)


def _exchange(**overrides):
    payload = dict(
        application_id="carsiportal",
        capture_source=CaptureSource.CHROME_DEVTOOLS,
        method="POST",
        url="https://carsi.example.com/api/products/123/stock?warehouse=fulya&token=secret-value",
        status_code=200,
        resource_type="fetch",
        request_content_type="application/json",
        response_content_type="application/json",
        user_action_ref="ui-action-stock-adjustment-1",
        auth_context_ref="managed-session:carsiportal",
        tenant_scope_ref="warehouse:fulya",
        authorization_header_present=True,
    )
    payload.update(overrides)
    return ObservedHttpExchange(**payload)


def test_groups_dynamic_resource_ids_and_never_retains_secret_query_values():
    first = _exchange()
    second = _exchange(
        capture_source=CaptureSource.PLAYWRIGHT_NETWORK,
        url="https://carsi.example.com/api/products/456/stock?warehouse=fulya&token=another-secret",
        user_action_ref="ui-action-stock-adjustment-2",
    )

    assert "secret-value" not in first.url
    assert "another-secret" not in second.url
    assert "token=" not in first.url
    assert "token=" not in second.url

    candidates = discover_api_candidates(
        [first, second],
        allowed_hosts={"carsi.example.com"},
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.path_template == "/api/products/{int}/stock"
    assert candidate.query_parameters == ("warehouse",)
    assert candidate.operation_kind is OperationKind.WRITE
    assert candidate.observation_count == 2
    assert candidate.eligible_for_promotion is True
    assert candidate.confidence >= 0.8


def test_write_without_correlated_user_action_is_not_promotion_eligible():
    candidate = discover_api_candidates(
        [_exchange(user_action_ref=None)], allowed_hosts={"carsi.example.com"}
    )[0]

    assert candidate.eligible_for_promotion is False
    assert "api_candidate_write_not_correlated_to_user_action" in candidate.blockers


def test_authenticated_exchange_requires_managed_auth_context_reference():
    candidate = discover_api_candidates(
        [_exchange(auth_context_ref=None)], allowed_hosts={"carsi.example.com"}
    )[0]

    assert candidate.eligible_for_promotion is False
    assert "api_candidate_auth_context_not_bound" in candidate.blockers


def test_non_allowlisted_host_is_ignored_instead_of_becoming_a_capability():
    candidates = discover_api_candidates(
        [_exchange(url="https://third-party.example.net/api/collect")],
        allowed_hosts={"carsi.example.com"},
    )
    assert candidates == []


def test_static_assets_are_not_misclassified_as_api_endpoints():
    candidates = discover_api_candidates(
        [
            _exchange(
                method="GET",
                url="https://carsi.example.com/assets/app.js",
                resource_type="script",
                request_content_type=None,
                response_content_type="application/javascript",
                user_action_ref=None,
                authorization_header_present=False,
            )
        ],
        allowed_hosts={"carsi.example.com"},
    )
    assert candidates == []


def test_unobserved_or_insecure_traffic_is_rejected_at_contract_boundary():
    with pytest.raises(ValueError, match="api_discovery_requires_observed_traffic"):
        _exchange(observed=False)

    with pytest.raises(ValueError, match="api_discovery_https_required"):
        _exchange(url="http://carsi.example.com/api/products/123/stock")


def test_ip_literal_target_is_rejected():
    with pytest.raises(ValueError, match="api_discovery_ip_literal_forbidden"):
        _exchange(url="https://10.10.10.10/api/products/123/stock")
