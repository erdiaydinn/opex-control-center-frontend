"""Trusted issuance bundle for one authorized tenant session.

This module intentionally exposes no HTTP route. Authentication completion code
may use it only after provider verification, external identity resolution and
membership authorization have succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .security import IdentitySigner


@dataclass(frozen=True)
class AuthorizedSessionAssertions:
    core_assertion: str
    ai_tenant_context_assertion: str


def issue_authorized_session_assertions(
    signer: IdentitySigner,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    actor_subject: str,
) -> AuthorizedSessionAssertions:
    """Issue audience-separated assertions from one authorized identity tuple.

    Keeping issuance in one primitive prevents tenant/membership drift between
    the Core identity assertion and the AI tenant-context assertion. The AI
    assertion remains purpose- and audience-bound and is not an end-user token.
    """

    core_assertion = signer.issue_internal_assertion(
        tenant_id=tenant_id,
        membership_id=membership_id,
    )
    ai_assertion = signer.issue_ai_tenant_context_assertion(
        tenant_id=tenant_id,
        membership_id=membership_id,
        actor_subject=actor_subject,
    )
    return AuthorizedSessionAssertions(
        core_assertion=core_assertion,
        ai_tenant_context_assertion=ai_assertion,
    )
