"""Fail-closed Core orchestration for tenant-grounded AI retrieval.

The Identity Gateway remains the signer and EAY AI Core remains the cryptographic
verifier/replay authority. Core adds a defense-in-depth binding check: the
short-lived AI assertion presented by trusted session orchestration must describe
the same tenant, membership and actor that Core freshly resolves from its own
authorization store before the assertion is forwarded to AI Core.

The JWT payload inspection in this module is deliberately *not* authentication.
Signature, issuer, audience lifetime and replay are still enforced by AI Core.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import httpx
import jwt

from app.core.ai_grounded_retrieval import retrieve_tenant_grounded_evidence
from app.core.ai_retrieval_authority import (
    AIRetrievalAuthorityDenied,
    resolve_authorized_ai_retrieval_identity,
)
from app.core.security import Principal

AI_TENANT_CONTEXT_TYP = "eay-ai-tenant-context+jwt"
AI_TENANT_CONTEXT_AUDIENCE = "eay-ai-core-grounded-retrieval"
AI_TENANT_CONTEXT_PURPOSE = "grounded-retrieval"
_ALLOWED_BINDING_CLAIMS = frozenset(
    {
        "iss",
        "aud",
        "sub",
        "tenant_id",
        "membership_id",
        "purpose",
        "jti",
        "iat",
        "nbf",
        "exp",
    }
)


class AITenantContextBindingDenied(RuntimeError):
    """The session assertion does not describe the fresh Core authority tuple."""


def _inspect_assertion_binding(assertion: str) -> tuple[UUID, UUID, str]:
    """Inspect an assertion only to compare identity binding before forwarding.

    This does not establish trust. AI Core performs the authoritative ES256/JWKS
    verification and single-use replay check after transport.
    """

    if (
        not assertion
        or len(assertion) > 8192
        or assertion != assertion.strip()
        or "," in assertion
        or any(character.isspace() for character in assertion)
    ):
        raise AITenantContextBindingDenied("AI tenant-context binding denied")

    try:
        header = jwt.get_unverified_header(assertion)
        claims = jwt.decode(
            assertion,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
            algorithms=["ES256"],
        )
    except jwt.PyJWTError as exc:
        raise AITenantContextBindingDenied(
            "AI tenant-context binding denied"
        ) from exc

    if (
        set(header) != {"alg", "kid", "typ"}
        or header.get("alg") != "ES256"
        or header.get("typ") != AI_TENANT_CONTEXT_TYP
        or not isinstance(header.get("kid"), str)
        or not header["kid"].strip()
    ):
        raise AITenantContextBindingDenied("AI tenant-context binding denied")

    if set(claims) != _ALLOWED_BINDING_CLAIMS:
        raise AITenantContextBindingDenied("AI tenant-context binding denied")
    if claims.get("aud") != AI_TENANT_CONTEXT_AUDIENCE:
        raise AITenantContextBindingDenied("AI tenant-context binding denied")
    if claims.get("purpose") != AI_TENANT_CONTEXT_PURPOSE:
        raise AITenantContextBindingDenied("AI tenant-context binding denied")

    actor = claims.get("sub")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 255:
        raise AITenantContextBindingDenied("AI tenant-context binding denied")

    try:
        tenant_id = UUID(str(claims["tenant_id"]))
        membership_id = UUID(str(claims["membership_id"]))
    except (TypeError, ValueError) as exc:
        raise AITenantContextBindingDenied(
            "AI tenant-context binding denied"
        ) from exc

    return tenant_id, membership_id, actor.strip()


async def retrieve_authorized_tenant_grounded_evidence(
    *,
    principal: Principal,
    tenant_context_assertion: str,
    base_url: str,
    message: str,
    as_of: date,
    layers: tuple[str, ...],
    limit: int = 8,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, object]]:
    """Freshly bind Core authorization to a session-issued AI assertion."""

    identity = await resolve_authorized_ai_retrieval_identity(principal)
    asserted_tenant, asserted_membership, asserted_actor = (
        _inspect_assertion_binding(tenant_context_assertion)
    )

    if (
        asserted_tenant != identity.tenant_id
        or asserted_membership != identity.membership_id
        or asserted_actor != identity.actor_subject
    ):
        raise AITenantContextBindingDenied("AI tenant-context binding denied")

    return await retrieve_tenant_grounded_evidence(
        base_url=base_url,
        tenant_context_assertion=tenant_context_assertion,
        message=message,
        as_of=as_of,
        layers=layers,
        limit=limit,
        client=client,
    )


__all__ = [
    "AIRetrievalAuthorityDenied",
    "AITenantContextBindingDenied",
    "retrieve_authorized_tenant_grounded_evidence",
]
