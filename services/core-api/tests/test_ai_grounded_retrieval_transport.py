from datetime import date

import httpx
import pytest

from app.core.ai_grounded_retrieval import (
    AIGroundedRetrievalUnavailable,
    AI_TENANT_CONTEXT_HEADER,
    retrieve_tenant_grounded_evidence,
)


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
        evidence = await retrieve_tenant_grounded_evidence(
            base_url="http://eay-ai-core:8000",
            tenant_context_assertion="signed.tenant.context",
            message="stock policy",
            as_of=date(2026, 8, 16),
            layers=("company", "operational"),
            client=client,
        )

    assert evidence == [VALID_EVIDENCE]
    assert observed["url"].endswith("/v1/internal/grounded/retrieve")
    assert observed["headers"][AI_TENANT_CONTEXT_HEADER.lower()] == "signed.tenant.context"
    assert "tenant_id" not in observed["body"]
    assert "membership_id" not in observed["body"]
    assert "actor" not in observed["body"]


@pytest.mark.asyncio
async def test_transport_fails_closed_on_ai_rejection():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "sensitive verifier detail"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieve_tenant_grounded_evidence(
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
        with pytest.raises(AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                client=client,
            )

    assert len(observed) == 1
    assert observed[0].url.host == "eay-ai-core"
    assert observed[0].headers[AI_TENANT_CONTEXT_HEADER] == "signed.tenant.context"


@pytest.mark.asyncio
async def test_transport_rejects_untrusted_request_shape_before_network():
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"evidence": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await retrieve_tenant_grounded_evidence(
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
            await retrieve_tenant_grounded_evidence(
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
            await retrieve_tenant_grounded_evidence(
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
        evidence = await retrieve_tenant_grounded_evidence(
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
            await retrieve_tenant_grounded_evidence(
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
        with pytest.raises(AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieve_tenant_grounded_evidence(
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
        with pytest.raises(AIGroundedRetrievalUnavailable, match="unavailable"):
            await retrieve_tenant_grounded_evidence(
                base_url="http://eay-ai-core:8000",
                tenant_context_assertion="signed.tenant.context",
                message="stock policy",
                as_of=date(2026, 8, 16),
                layers=("company",),
                limit=1,
                client=client,
            )
