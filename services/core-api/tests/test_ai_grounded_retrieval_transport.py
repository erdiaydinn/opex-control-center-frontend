from datetime import date

import httpx
import pytest

from app.core.ai_grounded_retrieval import (
    AI_TENANT_CONTEXT_HEADER,
    AIGroundedRetrievalUnavailable,
    retrieve_tenant_grounded_evidence,
)


@pytest.mark.asyncio
async def test_transport_sends_signed_context_without_tenant_parameter():
    observed = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["headers"] = dict(request.headers)
        observed["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"evidence": [{"id": "doc-a"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        evidence = await retrieve_tenant_grounded_evidence(
            base_url="http://eay-ai-core:8000",
            tenant_context_assertion="signed.tenant.context",
            message="stock policy",
            as_of=date(2026, 8, 16),
            layers=("company", "operational"),
            client=client,
        )

    assert evidence == [{"id": "doc-a"}]
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
