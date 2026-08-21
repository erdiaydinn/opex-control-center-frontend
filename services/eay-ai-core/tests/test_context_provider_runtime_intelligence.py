from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx
import pytest

from app.context_intelligence import ContextKind, ContextSourceClass
from app.context_provider_gateway import (
    ProviderRequestPlan,
    RequestPurpose,
    plan_provider_request,
)
from app.context_provider_registry import (
    PROVIDERS,
    ContextProviderSpec,
    ProviderAccessMode,
    ProviderReadiness,
)
from app.context_provider_runtime import (
    RUNTIME_POLICIES,
    ProviderRuntimeBlocked,
    ProviderRuntimePolicy,
    ProviderRuntimeUnavailable,
    execute_provider_request,
)

PROVIDER_ID = "test-live-weather"
URL = "https://api.example.test/v1/weather/hourly?city=istanbul"
NOW = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)


def provider_spec(
    *,
    provider_id: str = PROVIDER_ID,
    host: str = "api.example.test",
    production_enabled: bool = True,
    requires_secret: bool = False,
) -> ContextProviderSpec:
    return ContextProviderSpec(
        provider_id=provider_id,
        display_name="Test official weather",
        allowed_hosts=(host,),
        source_class=ContextSourceClass.OFFICIAL,
        access_mode=ProviderAccessMode.DOCUMENTED_WEB_SERVICE,
        context_kinds=(ContextKind.WEATHER,),
        requires_secret=requires_secret,
        continuous_ingestion_authorized=True,
        exact_adapter_verified=True,
        production_enabled=production_enabled,
        readiness=(
            ProviderReadiness.PRODUCTION_READY
            if production_enabled
            else ProviderReadiness.ADAPTER_READY_TO_BUILD
        ),
        evidence_refs=("test-evidence://provider-contract",),
    )


def runtime_policy(
    *,
    provider_id: str = PROVIDER_ID,
    max_response_bytes: int = 1024,
    secret_header_name: str | None = None,
) -> ProviderRuntimePolicy:
    return ProviderRuntimePolicy(
        provider_id=provider_id,
        adapter_id=f"{provider_id}-json",
        adapter_version="1",
        allowed_path_prefixes=("/v1/weather",),
        allowed_media_types=("application/json",),
        max_response_bytes=max_response_bytes,
        timeout_seconds=2.0,
        secret_header_name=secret_header_name,
        evidence_refs=("test-evidence://exact-adapter",),
    )


@pytest.fixture(autouse=True)
def governed_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PROVIDERS, PROVIDER_ID, provider_spec())
    monkeypatch.setitem(RUNTIME_POLICIES, PROVIDER_ID, runtime_policy())


def plan(*, url: str = URL, secret_ref: str | None = None) -> ProviderRequestPlan:
    return plan_provider_request(
        provider_id=PROVIDER_ID,
        url=url,
        purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        secret_ref=secret_ref,
    )


def test_verified_read_returns_external_evidence_receipt_without_company_claims() -> None:
    calls: list[httpx.Request] = []
    body = b'{"weather":"rain","intensity":"heavy"}'

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            content=body,
        )

    receipt = execute_provider_request(
        plan(),
        transport=httpx.MockTransport(handler),
        now=NOW,
    )

    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].headers["accept"] == "application/json"
    assert receipt.provider_id == PROVIDER_ID
    assert receipt.media_type == "application/json"
    assert receipt.raw_body == body
    assert receipt.body_sha256 == hashlib.sha256(body).hexdigest()
    assert receipt.byte_size == len(body)
    assert receipt.fetched_at == NOW
    fields = set(receipt.model_dump())
    assert "company_metric" not in fields
    assert "causal_claim" not in fields
    assert "execution_authority" not in fields


def test_evidence_fingerprint_is_stable_for_same_exact_external_payload() -> None:
    body = b'{"value":42}'

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    first = execute_provider_request(plan(), transport=httpx.MockTransport(handler), now=NOW)
    second = execute_provider_request(plan(), transport=httpx.MockTransport(handler), now=NOW)

    assert first.evidence_fingerprint == second.evidence_fingerprint
    assert first.body_sha256 == second.body_sha256


def test_production_disabled_provider_is_blocked_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PROVIDERS, PROVIDER_ID, provider_spec(production_enabled=False))
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    blocked_plan = plan()
    assert blocked_plan.execution_permitted is False
    assert "provider_production_not_enabled" in blocked_plan.blockers

    with pytest.raises(ProviderRuntimeBlocked, match="request_plan_not_executable"):
        execute_provider_request(blocked_plan, transport=httpx.MockTransport(handler), now=NOW)

    assert calls == 0


def test_runtime_requires_exact_code_reviewed_policy_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(RUNTIME_POLICIES, PROVIDER_ID)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    with pytest.raises(ProviderRuntimeBlocked, match="exact_policy_missing"):
        execute_provider_request(plan(), transport=httpx.MockTransport(handler), now=NOW)

    assert calls == 0


def test_runtime_revalidates_path_and_sensitive_query_before_network() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    with pytest.raises(ProviderRuntimeBlocked, match="path_not_allowlisted"):
        execute_provider_request(
            plan(url="https://api.example.test/admin/secrets"),
            transport=httpx.MockTransport(handler),
            now=NOW,
        )

    forged = ProviderRequestPlan(
        provider_id=PROVIDER_ID,
        url="https://api.example.test/v1/weather/hourly?token=should-never-leave",
        purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        execution_permitted=True,
    )
    with pytest.raises(ProviderRuntimeBlocked, match="secret_in_query_forbidden"):
        execute_provider_request(forged, transport=httpx.MockTransport(handler), now=NOW)

    assert calls == 0


def test_redirect_is_never_followed() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={
                "location": "https://untrusted.example/collect",
                "content-type": "application/json",
            },
            content=b"{}",
        )

    with pytest.raises(ProviderRuntimeBlocked, match="redirect_forbidden"):
        execute_provider_request(plan(), transport=httpx.MockTransport(handler), now=NOW)

    assert calls == [URL]


def test_unexpected_content_type_and_oversized_response_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def html_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html />")

    with pytest.raises(ProviderRuntimeBlocked, match="content_type_not_allowlisted"):
        execute_provider_request(plan(), transport=httpx.MockTransport(html_handler), now=NOW)

    monkeypatch.setitem(RUNTIME_POLICIES, PROVIDER_ID, runtime_policy(max_response_bytes=8))

    def large_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=httpx.ByteStream(b"123456789"),
        )

    with pytest.raises(ProviderRuntimeBlocked, match="response_too_large"):
        execute_provider_request(plan(), transport=httpx.MockTransport(large_handler), now=NOW)


def test_non_success_response_is_not_reinterpreted_as_evidence() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"content-type": "application/json"}, content=b"{}")

    with pytest.raises(ProviderRuntimeUnavailable, match="upstream_non_success"):
        execute_provider_request(plan(), transport=httpx.MockTransport(handler), now=NOW)


def test_secret_is_only_sent_through_reviewed_header_and_never_enters_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_provider_id = "test-secret-provider"
    secret = "super-secret-provider-token"
    monkeypatch.setitem(
        PROVIDERS,
        secret_provider_id,
        provider_spec(
            provider_id=secret_provider_id,
            production_enabled=True,
            requires_secret=True,
        ),
    )
    monkeypatch.setitem(
        RUNTIME_POLICIES,
        secret_provider_id,
        runtime_policy(
            provider_id=secret_provider_id,
            secret_header_name="X-Provider-Key",
        ),
    )

    request_plan = plan_provider_request(
        provider_id=secret_provider_id,
        url=URL,
        purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        secret_ref="secret://runtime/provider-key",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-provider-key"] == secret
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    receipt = execute_provider_request(
        request_plan,
        secret_value=secret,
        transport=httpx.MockTransport(handler),
        now=NOW,
    )

    assert secret not in repr(receipt.model_dump())
    assert receipt.source_url == URL


def test_public_provider_rejects_unexpected_secret_before_network() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    with pytest.raises(ProviderRuntimeBlocked, match="unexpected_secret_material"):
        execute_provider_request(
            plan(),
            secret_value="should-not-be-sent",
            transport=httpx.MockTransport(handler),
            now=NOW,
        )

    assert calls == 0
