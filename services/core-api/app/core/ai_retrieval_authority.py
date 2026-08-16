"""Server-authoritative identity binding for Core -> EAY AI retrieval.

This module deliberately accepts only an already authenticated Core Principal.
Tenant, membership and Jarvis authorization are resolved again from the
authoritative Core authorization store; callers cannot provide or override them.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.permission_catalog import action_permission, module_permission
from app.core.resources import resolve_principal_access
from app.core.security import Principal


class AIRetrievalAuthorityDenied(RuntimeError):
    """The authenticated principal no longer has active retrieval authority."""


class AIRetrievalAuthorityUnavailable(RuntimeError):
    """The authoritative membership binding cannot be resolved safely."""


@dataclass(frozen=True)
class AuthorizedAIRetrievalIdentity:
    tenant_id: UUID
    membership_id: UUID
    actor_subject: str


_REQUIRED_RETRIEVAL_PERMISSIONS = frozenset(
    {
        module_permission("jarvis"),
        action_permission("jarvis", "ask"),
    }
)


async def resolve_authorized_ai_retrieval_identity(
    principal: Principal,
) -> AuthorizedAIRetrievalIdentity:
    """Resolve a fresh, immutable AI retrieval identity from Core authority.

    The caller supplies no tenant or membership identifier. This intentionally
    re-checks Core membership and Jarvis permissions immediately before trusted
    AI orchestration so a stale authenticated request cannot manufacture a
    retrieval identity after access has been revoked.
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

    fresh_permissions = {
        str(item.get("key", "")).strip()
        for item in access.get("permission_assignments", ())
        if isinstance(item, dict)
    }
    if not _REQUIRED_RETRIEVAL_PERMISSIONS.issubset(fresh_permissions):
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
