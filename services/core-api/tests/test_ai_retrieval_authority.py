from __future__ import annotations

import inspect
from uuid import UUID

import pytest

from app.core.ai_retrieval_authority import (
    AIRetrievalAuthorityDenied,
    AIRetrievalAuthorityUnavailable,
    resolve_authorized_ai_retrieval_identity,
)
from app.core.security import Principal

TENANT_ID = UUID("00000000-0000-0000-0000-00000000a001")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-00000000a101")
JARVIS_PERMISSIONS = (
    {"key": "module:jarvis:view", "role_key": "operator", "scope": {}},
    {"key": "action:jarvis:ask", "role_key": "operator", "scope": {}},
)


def principal() -> Principal:
    return Principal(
        subject="operator@example.test",
        tenant_id=TENANT_ID,
        roles=("viewer",),
        auth_mode="oidc",
    )


def test_resolver_signature_accepts_no_client_tenant_or_membership_override() -> None:
    parameters = inspect.signature(
        resolve_authorized_ai_retrieval_identity
    ).parameters
    assert tuple(parameters) == ("principal",)


@pytest.mark.asyncio
async def test_identity_comes_from_fresh_core_membership_authority(monkeypatch) -> None:
    observed: dict[str, str] = {}

    async def fake_resolve_principal_access(*, tenant_id: str, subject: str):
        observed["tenant_id"] = tenant_id
        observed["subject"] = subject
        return {
            "tenant_status": "active",
            "membership_status": "active",
            "membership_id": str(MEMBERSHIP_ID),
            "roles": ("operator",),
            "permission_assignments": JARVIS_PERMISSIONS,
        }

    monkeypatch.setattr(
        "app.core.ai_retrieval_authority.resolve_principal_access",
        fake_resolve_principal_access,
    )

    identity = await resolve_authorized_ai_retrieval_identity(principal())

    assert identity.tenant_id == TENANT_ID
    assert identity.membership_id == MEMBERSHIP_ID
    assert identity.actor_subject == "operator@example.test"
    assert observed == {
        "tenant_id": str(TENANT_ID),
        "subject": "operator@example.test",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("permission_assignments"),
    (
        (),
        (JARVIS_PERMISSIONS[0],),
        (JARVIS_PERMISSIONS[1],),
    ),
)
async def test_fresh_jarvis_permission_revocation_fails_closed(
    monkeypatch,
    permission_assignments,
) -> None:
    async def fake_resolve_principal_access(*, tenant_id: str, subject: str):
        del tenant_id, subject
        return {
            "tenant_status": "active",
            "membership_status": "active",
            "membership_id": str(MEMBERSHIP_ID),
            "roles": ("operator",),
            "permission_assignments": permission_assignments,
        }

    monkeypatch.setattr(
        "app.core.ai_retrieval_authority.resolve_principal_access",
        fake_resolve_principal_access,
    )

    with pytest.raises(AIRetrievalAuthorityDenied):
        await resolve_authorized_ai_retrieval_identity(principal())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tenant_status", "membership_status"),
    (("suspended", "active"), ("active", "suspended")),
)
async def test_inactive_authority_fails_closed(
    monkeypatch,
    tenant_status: str,
    membership_status: str,
) -> None:
    async def fake_resolve_principal_access(*, tenant_id: str, subject: str):
        del tenant_id, subject
        return {
            "tenant_status": tenant_status,
            "membership_status": membership_status,
            "membership_id": str(MEMBERSHIP_ID),
            "roles": (),
            "permission_assignments": JARVIS_PERMISSIONS,
        }

    monkeypatch.setattr(
        "app.core.ai_retrieval_authority.resolve_principal_access",
        fake_resolve_principal_access,
    )

    with pytest.raises(AIRetrievalAuthorityDenied):
        await resolve_authorized_ai_retrieval_identity(principal())


@pytest.mark.asyncio
async def test_invalid_membership_identity_fails_closed(monkeypatch) -> None:
    async def fake_resolve_principal_access(*, tenant_id: str, subject: str):
        del tenant_id, subject
        return {
            "tenant_status": "active",
            "membership_status": "active",
            "membership_id": "not-a-uuid",
            "roles": (),
            "permission_assignments": JARVIS_PERMISSIONS,
        }

    monkeypatch.setattr(
        "app.core.ai_retrieval_authority.resolve_principal_access",
        fake_resolve_principal_access,
    )

    with pytest.raises(AIRetrievalAuthorityUnavailable):
        await resolve_authorized_ai_retrieval_identity(principal())


@pytest.mark.asyncio
async def test_authorization_backend_failure_never_degrades_open(monkeypatch) -> None:
    async def fake_resolve_principal_access(*, tenant_id: str, subject: str):
        del tenant_id, subject
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "app.core.ai_retrieval_authority.resolve_principal_access",
        fake_resolve_principal_access,
    )

    with pytest.raises(AIRetrievalAuthorityUnavailable):
        await resolve_authorized_ai_retrieval_identity(principal())
