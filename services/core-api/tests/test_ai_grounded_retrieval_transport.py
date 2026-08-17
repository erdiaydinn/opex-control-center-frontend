import json
from datetime import date
from importlib import import_module

import httpx
import pytest

retrieval = import_module("app.core.ai_grounded_retrieval")


VALID_EVIDENCE = {
    "id": "doc-a",
    "layer": "company",
    "title": "Stock policy",
    "excerpt": "Canonical stock policy evidence.",
    "source_name": "EAY policy",
    "source_url": None,
    "effective_from": "2026-01-01",
    "effective_to": None,
    "authority_level": "company",
    "score": 0.9,
}


@pytest.mark.asyncio
async def test_transport_sends_signed_context_without_tenant_parameter():
    observed = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["headers"] = dict(request.headers)
        observed["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"evidence": [VALID_EVIDENCE]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        evidence = await retrieval.retrieve_tenant_grounded_evidence(
            base_url="http://eay-ai-core:8000",
            tenant_context_assertion="signed.tenant.context",
            message="stock policy",
            as_of=date(2026, 8, 16),
            layers=("company", "operational"),
            client=client,
        )

    assert evidence == [VALID_EVIDENCE]
    assert observed["url"].endswith("/v1/internal/grounded/retrieve")
    assert (
        observed["headers"][retrieval.AI_TENANT_CONTEXT_HEADER.lower()]
        == "signed.tenant.context"
    )
    assert "tenant_id" not in observed["body"]
    assert "membership_id" not in observed["body"]
    assert "actor" not in observed["body"]


@pytest.mark.asyncio
async def test_transport_fails_closed_on_ai_rejection():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "sensitive verifier detail"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )


@pytest.mark.asyncio
async def test_transport_never_forwards_assertion_across_redirect():
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.host == "eay-ai-core":
            return httpx.Response(
                307,
                headers={
                    "location": "https://attacker.example/v1/internal/grounded/retrieve"
                },
            )
        return httpx.Response(200, json={"evidence": [VALID_EVIDENCE]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=True,
    ) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )

    assert len(observed) == 1
    assert observed[0].url.host == "eay-ai-core"
    assert observed[0].headers[retrieval.AI_TENANT_CONTEXT_HEADER] == "signed.tenant.context"


@pytest.mark.asyncio
async def test_transport_rejects_untrusted_request_shape_before_network():
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"evidence": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://user:secret@eay-ai-core:8000",
                tenant_context_assertion=" signed.tenant.context",
                message="x",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )

    assert called is False


@pytest.mark.asyncio
async def test_transport_rejects_duplicate_layers_before_network():
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"evidence": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="layers"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company", "company"),
                client=client,
            )

    assert called is False


@pytest.mark.asyncio
async def test_transport_rejects_untrusted_origin_before_credential_forwarding():
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"evidence": [VALID_EVIDENCE]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="base URL"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="https://attacker.example",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )

    assert called is False


@pytest.mark.asyncio
async def test_transport_requires_explicit_trust_for_non_default_internal_host():
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"evidence": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        evidence = await retrieval.retrieve_tenant_grounded_evidence(
            base_url="https://ai-core.internal",
            tenant_context_assertion="signed.tenant.context",
            message="stock policy",
            as_of=date(2026, 8, 16),
            layers=("company",),
            client=client,
            trusted_hosts=frozenset({"ai-core.internal"}),
        )

    assert evidence == []
    assert len(observed) == 1
    assert observed[0].url.host == "ai-core.internal"


@pytest.mark.asyncio
async def test_transport_rejects_base_url_path_before_network():
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"evidence": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="base URL"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000/alternate",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )

    assert called is False


@pytest.mark.asyncio
async def test_transport_rejects_scope_fields_in_ai_evidence_response():
    leaked = {**VALID_EVIDENCE, "tenant_id": "00000000-0000-0000-0000-0000000000a1"}

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"evidence": [leaked]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )


@pytest.mark.asyncio
async def test_transport_rejects_evidence_count_above_requested_limit():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"evidence": [VALID_EVIDENCE, VALID_EVIDENCE]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                limit=1,
                client=client,
            )


@pytest.mark.asyncio
async def test_transport_rejects_evidence_outside_requested_layers():
    unexpected = {
        **VALID_EVIDENCE,
        "layer": "operational",
        "authority_level": "operational",
    }

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"evidence": [unexpected]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="legal requirements",
                as_of=date(2026, 8, 16),
                layers=("legal",),
                client=client,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.01, 1.01])
async def test_transport_rejects_invalid_evidence_score(score: float):
    unsafe = {**VALID_EVIDENCE, "score": score}

    async def handler(_: httpx.Request) -> httpx.Response:
        wire_body = json.dumps({"evidence": [unsafe]}, allow_nan=True).encode("utf-8")
        return httpx.Response(
            200,
            content=wire_body,
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:secret@example.com/policy",
    ],
)
async def test_transport_rejects_unsafe_evidence_source_url(source_url: str):
    unsafe = {**VALID_EVIDENCE, "source_url": source_url}

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"evidence": [unsafe]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("effective_from", ["2026-02-30", "2026-8-01", "not-a-date"])
async def test_transport_rejects_invalid_evidence_effective_date(effective_from: str):
    unsafe = {**VALID_EVIDENCE, "effective_from": effective_from}

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"evidence": [unsafe]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )


@pytest.mark.asyncio
async def test_transport_rejects_inverted_evidence_effective_window():
    unsafe = {
        **VALID_EVIDENCE,
        "effective_from": "2026-09-01",
        "effective_to": "2026-08-01",
    }

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"evidence": [unsafe]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(retrieval.AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieval.retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )
