"""Server-authoritative identity binding for Core -> EAY AI retrieval.

This module deliberately accepts only an already authenticated Core Principal.
Tenant and membership identifiers are resolved again from the authoritative Core
authorization store; callers cannot provide or override them.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.resources import resolve_principal_access
from app.core.security import Principal


class AIRetrievalAuthorityDenied(RuntimeError):
    """The authenticated principal no longer has active tenant membership."""


class AIRetrievalAuthorityUnavailable(RuntimeError):
    """The authoritative membership binding cannot be resolved safely."""


@dataclass(frozen=True)
class AuthorizedAIRetrievalIdentity:
    tenant_id: UUID
    membership_id: UUID
    actor_subject: str


async def resolve_authorized_ai_retrieval_identity(
    principal: Principal,
) -> AuthorizedAIRetrievalIdentity:
    """Resolve a fresh, immutable AI retrieval identity from Core authority.

    The caller supplies no tenant or membership identifier. This intentionally
    re-checks Core membership state immediately before trusted AI orchestration
    so a stale authenticated request cannot manufacture a retrieval identity.
    """

    actor_subject = principal.subject.strip()
    if not actor_subject:
        raise AIRetrievalAuthorityDenied("AI retrieval authority denied")

    try:
        access = await resolve_principal_access(
            tenant_id=str(principal.tenant_id),
            subject=actor_subject,
        )
    except Exception as exc:
        raise AIRetrievalAuthorityUnavailable(
            "AI retrieval authority unavailable"
        ) from exc

    if (
        access is None
        or access.get("tenant_status") != "active"
        or access.get("membership_status") != "active"
    ):
        raise AIRetrievalAuthorityDenied("AI retrieval authority denied")

    try:
        membership_id = UUID(str(access.get("membership_id", "")))
    except (TypeError, ValueError) as exc:
        raise AIRetrievalAuthorityUnavailable(
            "AI retrieval authority unavailable"
        ) from exc

    return AuthorizedAIRetrievalIdentity(
        tenant_id=principal.tenant_id,
        membership_id=membership_id,
        actor_subject=actor_subject,
    )
