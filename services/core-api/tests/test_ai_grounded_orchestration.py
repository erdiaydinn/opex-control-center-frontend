from __future__ import annotations

import base64
import json
from datetime import date
from uuid import UUID

import pytest

from app.core.ai_grounded_orchestration import (
    AITenantContextBindingDenied,
    retrieve_authorized_tenant_grounded_evidence,
)
from app.core.ai_retrieval_authority import AuthorizedAIRetrievalIdentity
from app.core.security import Principal

TENANT_A = UUID("00000000-0000-0000-0000-00000000a001")
TENANT_B = UUID("00000000-0000-0000-0000-00000000b001")
MEMBERSHIP_A = UUID("10000000-0000-0000-0000-00000000a001")
MEMBERSHIP_B = UUID("10000000-0000-0000-0000-00000000b001")
ACTOR_A = "actor-a"


def _segment(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def assertion(
    *,
    tenant_id: UUID = TENANT_A,
    membership_id: UUID = MEMBERSHIP_A,
    actor: str = ACTOR_A,
    audience: str = "eay-ai-core-grounded-retrieval",
    purpose: str = "grounded-retrieval",
) -> str:
    header = {
        "alg": "ES256",
        "kid": "test-key",
        "typ": "eay-ai-tenant-context+jwt",
    }
    claims = {
        "iss": "https://identity.test",
        "aud": audience,
        "sub": actor,
        "tenant_id": str(tenant_id),
        "membership_id": str(membership_id),
        "purpose": purpose,
        "jti": "0123456789abcdef0123456789abcdef",
        "iat": 1,
        "nbf": 1,
        "exp": 60,
    }
    return f"{_segment(header)}.{_segment(claims)}.AA"


@pytest.fixture
def principal() -> Principal:
    return Principal(
        subject=ACTOR_A,
        tenant_id=TENANT_A,
        roles=("viewer",),
        auth_mode="internal_assertion",
    )


@pytest.mark.asyncio
async def test_matching_binding_reaches_transport(
    monkeypatch,
    principal,
) -> None:
    async def resolve(_principal):
        return AuthorizedAIRetrievalIdentity(
            tenant_id=TENANT_A,
            membership_id=MEMBERSHIP_A,
            actor_subject=ACTOR_A,
        )

    calls: list[dict[str, object]] = []

    async def retrieve(**kwargs):
        calls.append(kwargs)
        return [{"id": "evidence-a"}]

    monkeypatch.setattr(
        "app.core.ai_grounded_orchestration."
        "resolve_authorized_ai_retrieval_identity",
        resolve,
    )
    monkeypatch.setattr(
        "app.core.ai_grounded_orchestration."
        "retrieve_tenant_grounded_evidence",
        retrieve,
    )

    token = assertion()
    result = await retrieve_authorized_tenant_grounded_evidence(
        principal=principal,
        tenant_context_assertion=token,
        base_url="http://eay-ai-core:8090",
        message="show policy evidence",
        as_of=date(2026, 8, 16),
        layers=("company",),
    )

    assert result == [{"id": "evidence-a"}]
    assert len(calls) == 1
    assert calls[0]["tenant_context_assertion"] == token
    assert "tenant_id" not in calls[0]
    assert "membership_id" not in calls[0]
    assert "actor" not in calls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        assertion(tenant_id=TENANT_B),
        assertion(membership_id=MEMBERSHIP_B),
        assertion(actor="actor-b"),
        assertion(audience="opex-core-api"),
        assertion(purpose="other-purpose"),
    ],
)
async def test_binding_mismatch_fails_before_transport(
    monkeypatch,
    principal,
    token,
) -> None:
    async def resolve(_principal):
        return AuthorizedAIRetrievalIdentity(
            tenant_id=TENANT_A,
            membership_id=MEMBERSHIP_A,
            actor_subject=ACTOR_A,
        )

    async def retrieve(**_kwargs):
        raise AssertionError(
            "transport must not run for a mismatched binding"
        )

    monkeypatch.setattr(
        "app.core.ai_grounded_orchestration."
        "resolve_authorized_ai_retrieval_identity",
        resolve,
    )
    monkeypatch.setattr(
        "app.core.ai_grounded_orchestration."
        "retrieve_tenant_grounded_evidence",
        retrieve,
    )

    with pytest.raises(AITenantContextBindingDenied):
        await retrieve_authorized_tenant_grounded_evidence(
            principal=principal,
            tenant_context_assertion=token,
            base_url="http://eay-ai-core:8090",
            message="show policy evidence",
            as_of=date(2026, 8, 16),
            layers=("company",),
        )
