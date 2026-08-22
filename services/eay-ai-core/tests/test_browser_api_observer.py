import pytest

from app.api_discovery_intelligence import CaptureSource
from app.api_schema_intelligence import ApiProtocol, GraphQLOperationKind
from app.browser_api_observer import observe_browser_exchange


def test_browser_observer_discards_header_and_payload_values_but_keeps_structure():
    observation = observe_browser_exchange(
        application_id="carsiportal",
        capture_source=CaptureSource.CHROME_DEVTOOLS,
        method="POST",
        url="https://carsi.example.com/api/inventory/adjustments?warehouse=fulya&token=url-secret",
        status_code=200,
        allowed_hosts={"carsi.example.com"},
        resource_type="fetch",
        request_headers={
            "Authorization": "Bearer never-retain-this",
            "Cookie": "session=never-retain-cookie",
            "Content-Type": "application/json",
        },
        response_headers={"Set-Cookie": "sid=never-retain-response-cookie"},
        request_content_type="application/json",
        response_content_type="application/json",
        request_payload={
            "warehouse": "fulya",
            "barcode": "8691234567890",
            "quantity": 3,
            "reason": "ZAYI",
        },
        response_payload={"transactionId": "TX-123", "stock": 24},
        tenant_scope_ref="warehouse:fulya",
        auth_context_ref="managed-session:carsiportal",
    )

    serialized = observation.model_dump_json()
    assert observation.exchange.authorization_header_present is True
    assert observation.exchange.cookie_header_present is True
    assert observation.exchange.query_parameter_names() == ("warehouse",)
    assert "url-secret" not in serialized
    assert "never-retain-this" not in serialized
    assert "never-retain-cookie" not in serialized
    assert "never-retain-response-cookie" not in serialized
    assert "8691234567890" not in serialized
    assert "ZAYI" not in serialized
    assert "TX-123" not in serialized
    assert observation.raw_headers_retained is False
    assert observation.raw_payloads_retained is False
    assert observation.request_schema is not None
    assert observation.request_schema.protocol is ApiProtocol.JSON_HTTP


def test_browser_observer_understands_graphql_without_retaining_document():
    observation = observe_browser_exchange(
        application_id="carsiportal",
        capture_source=CaptureSource.PLAYWRIGHT_NETWORK,
        method="POST",
        url="https://carsi.example.com/graphql",
        status_code=200,
        allowed_hosts={"carsi.example.com"},
        resource_type="xhr",
        request_content_type="application/json",
        response_content_type="application/json",
        request_payload={
            "operationName": "AdjustInventory",
            "query": "mutation AdjustInventory($qty: Int!) { adjustInventory(qty: $qty) { id } }",
            "variables": {"qty": 3},
        },
        response_payload={"data": {"adjustInventory": {"id": "TX-1"}}},
        tenant_scope_ref="warehouse:fulya",
        auth_context_ref="managed-session:carsiportal",
    )

    assert observation.request_schema is not None
    assert observation.request_schema.protocol is ApiProtocol.GRAPHQL
    assert observation.request_schema.graphql_operation_kind is GraphQLOperationKind.MUTATION
    assert observation.request_schema.graphql_operation_name == "AdjustInventory"
    assert "adjustInventory(qty" not in observation.model_dump_json()


def test_browser_observer_rejects_non_allowlisted_host_and_non_browser_capture_source():
    with pytest.raises(ValueError, match="browser_api_observer_host_not_allowlisted"):
        observe_browser_exchange(
            application_id="carsiportal",
            capture_source=CaptureSource.CHROME_DEVTOOLS,
            method="GET",
            url="https://tracker.example.net/collect",
            status_code=204,
            allowed_hosts={"carsi.example.com"},
        )

    with pytest.raises(ValueError, match="browser_api_observer_capture_source_not_browser_managed"):
        observe_browser_exchange(
            application_id="carsiportal",
            capture_source=CaptureSource.MITMPROXY,
            method="GET",
            url="https://carsi.example.com/api/stock",
            status_code=200,
            allowed_hosts={"carsi.example.com"},
        )
