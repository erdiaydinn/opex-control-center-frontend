from app.api_action_correlation import (
    TimedExchange,
    UiActionKind,
    UiActionObservation,
    correlate_ui_action,
)
from app.api_discovery_intelligence import CaptureSource, ObservedHttpExchange


def _exchange(method: str, url: str, **overrides):
    payload = dict(
        application_id="carsiportal",
        capture_source=CaptureSource.CHROME_DEVTOOLS,
        method=method,
        url=url,
        status_code=200,
        resource_type="fetch",
        request_content_type="application/json",
        response_content_type="application/json",
        auth_context_ref="managed-session:carsiportal",
        tenant_scope_ref="warehouse:fulya",
        authorization_header_present=True,
    )
    payload.update(overrides)
    return ObservedHttpExchange(**payload)


def _action():
    return UiActionObservation(
        action_ref="stock-adjust-click-1",
        application_id="carsiportal",
        started_at_ms=10_000,
        completed_at_ms=11_000,
        action_kind=UiActionKind.WRITE,
        tenant_scope_ref="warehouse:fulya",
        managed_auth_context_ref="managed-session:carsiportal",
    )


def test_write_action_correlates_to_mutating_request_not_background_read():
    decision = correlate_ui_action(
        _action(),
        [
            TimedExchange(
                exchange=_exchange("GET", "https://carsi.example.com/api/notifications"),
                observed_at_ms=10_950,
            ),
            TimedExchange(
                exchange=_exchange("POST", "https://carsi.example.com/api/inventory/adjustments"),
                observed_at_ms=11_050,
            ),
        ],
    )

    assert decision.correlated is True
    assert decision.ambiguous is False
    assert decision.selected_exchange is not None
    assert decision.selected_exchange.method == "POST"
    assert decision.selected_exchange.user_action_ref == "stock-adjust-click-1"


def test_two_equally_plausible_mutations_fail_closed_as_ambiguous():
    decision = correlate_ui_action(
        _action(),
        [
            TimedExchange(
                exchange=_exchange("POST", "https://carsi.example.com/api/inventory/adjustments"),
                observed_at_ms=11_010,
            ),
            TimedExchange(
                exchange=_exchange("POST", "https://carsi.example.com/api/audit/events"),
                observed_at_ms=11_020,
            ),
        ],
    )

    assert decision.correlated is False
    assert decision.ambiguous is True
    assert "api_action_correlation_ambiguous" in decision.blockers


def test_tenant_scope_match_beats_cross_tenant_candidate():
    decision = correlate_ui_action(
        _action(),
        [
            TimedExchange(
                exchange=_exchange(
                    "POST",
                    "https://carsi.example.com/api/inventory/adjustments",
                    tenant_scope_ref="warehouse:kadikoy",
                ),
                observed_at_ms=11_000,
            ),
            TimedExchange(
                exchange=_exchange("POST", "https://carsi.example.com/api/inventory/adjustments"),
                observed_at_ms=11_100,
            ),
        ],
    )

    assert decision.correlated is True
    assert decision.selected_exchange is not None
    assert decision.selected_exchange.tenant_scope_ref == "warehouse:fulya"


def test_requests_outside_bounded_action_window_are_not_correlated():
    decision = correlate_ui_action(
        _action(),
        [
            TimedExchange(
                exchange=_exchange("POST", "https://carsi.example.com/api/inventory/adjustments"),
                observed_at_ms=30_000,
            )
        ],
    )

    assert decision.correlated is False
    assert "api_action_no_network_candidate_in_window" in decision.blockers


def test_low_semantic_match_does_not_get_silently_bound():
    decision = correlate_ui_action(
        _action(),
        [
            TimedExchange(
                exchange=_exchange(
                    "GET",
                    "https://carsi.example.com/api/background/config",
                    resource_type="document",
                    status_code=500,
                    tenant_scope_ref="warehouse:kadikoy",
                    auth_context_ref="other-session",
                ),
                observed_at_ms=11_100,
            )
        ],
    )

    assert decision.correlated is False
    assert "api_action_correlation_below_threshold" in decision.blockers
