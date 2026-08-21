from uuid import UUID

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

import app.core.security as security
from app.core.config import Settings
from app.core.security import _decode_development_token, get_current_principal

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_production_rejects_development_auth() -> None:
    with pytest.raises(ValueError, match="Staging and production require"):
        Settings(environment="production", auth_mode="development")


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="Wildcard CORS"):
        Settings(
            environment="production",
            auth_mode="oidc",
            oidc_issuer="https://identity.example.com",
            oidc_audience="opex-core-api",
            oidc_jwks_url="https://identity.example.com/.well-known/jwks.json",
            cors_origins="*",
        )


def test_runtime_and_migration_credentials_must_differ() -> None:
    shared_url = "postgresql+asyncpg://shared:shared@postgres:5432/opex"

    with pytest.raises(ValueError, match="credentials must differ"):
        Settings(
            database_url=shared_url,
            migration_database_url=shared_url,
        )


def test_development_token_carries_tenant_context() -> None:
    principal = _decode_development_token(
        f"dev.user-1.{TENANT_ID}.inventory_admin,viewer"
    )

    assert principal.subject == "user-1"
    assert principal.tenant_id == TENANT_ID
    assert principal.roles == ("inventory_admin", "viewer")


def test_development_token_rejects_missing_tenant() -> None:
    with pytest.raises(HTTPException):
        _decode_development_token("dev.user-1..viewer")


def test_development_token_rejects_non_uuid_tenant() -> None:
    with pytest.raises(HTTPException):
        _decode_development_token("dev.user-1.tenant-a.viewer")


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/context",
            "headers": [],
        }
    )


def make_credentials(subject: str, role: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=f"dev.{subject}.{TENANT_ID}.{role}",
    )


@pytest.mark.asyncio
async def test_database_roles_override_token_roles(monkeypatch) -> None:
    async def fake_resolve_principal_access(**kwargs):
        return {
            "tenant_status": "active",
            "membership_id": "00000000-0000-0000-0000-000000000099",
            "membership_status": "active",
            "roles": ("viewer",),
            "permission_assignments": (),
        }

    monkeypatch.setattr(
        security,
        "resolve_principal_access",
        fake_resolve_principal_access,
    )

    principal = await get_current_principal(
        make_request(),
        make_credentials("user-1", "super_admin"),
        Settings(environment="development", auth_mode="development"),
    )

    assert principal.roles == ("viewer",)
    assert "super_admin" not in principal.roles


@pytest.mark.asyncio
async def test_suspended_membership_is_denied(monkeypatch) -> None:
    async def fake_resolve_principal_access(**kwargs):
        return {
            "tenant_status": "active",
            "membership_id": "00000000-0000-0000-0000-000000000099",
            "membership_status": "suspended",
            "roles": ("viewer",),
            "permission_assignments": (),
        }

    monkeypatch.setattr(
        security,
        "resolve_principal_access",
        fake_resolve_principal_access,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(
            make_request(),
            make_credentials("user-1", "viewer"),
            Settings(environment="development", auth_mode="development"),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_unknown_membership_is_denied(monkeypatch) -> None:
    async def fake_resolve_principal_access(**kwargs):
        return None

    monkeypatch.setattr(
        security,
        "resolve_principal_access",
        fake_resolve_principal_access,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(
            make_request(),
            make_credentials("unknown-user", "super_admin"),
            Settings(environment="development", auth_mode="development"),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_suspended_tenant_is_denied(monkeypatch) -> None:
    async def fake_resolve_principal_access(**kwargs):
        return {
            "tenant_status": "suspended",
            "membership_id": "00000000-0000-0000-0000-000000000099",
            "membership_status": "active",
            "roles": ("viewer",),
            "permission_assignments": (),
        }

    monkeypatch.setattr(
        security,
        "resolve_principal_access",
        fake_resolve_principal_access,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(
            make_request(),
            make_credentials("user-1", "viewer"),
            Settings(environment="development", auth_mode="development"),
        )

    assert exc_info.value.status_code == 403



def test_production_requires_database_secret_file(monkeypatch) -> None:
    monkeypatch.delenv("OPEX_DATABASE_URL", raising=False)
    monkeypatch.delenv("OPEX_MIGRATION_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="secret files"):
        Settings(
            environment="production",
            auth_mode="oidc",
            oidc_issuer="https://identity.example.com",
            oidc_audience="opex-core-api",
            oidc_jwks_url="https://identity.example.com/.well-known/jwks.json",
            allowed_hosts="app.example.com",
            cors_origins="https://app.example.com",
        )


def test_production_reads_runtime_database_secret_file(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPEX_DATABASE_URL", raising=False)
    monkeypatch.delenv("OPEX_MIGRATION_DATABASE_URL", raising=False)

    secret_file = tmp_path / "runtime-database-url"
    secret_file.write_text(
        "postgresql+asyncpg://runtime:test@postgres:5432/opex",
        encoding="utf-8",
    )

    settings = Settings(
        environment="production",
        auth_mode="oidc",
        oidc_issuer="https://identity.example.com",
        oidc_audience="opex-core-api",
        oidc_jwks_url="https://identity.example.com/.well-known/jwks.json",
        allowed_hosts="app.example.com",
        cors_origins="https://app.example.com",
        database_url_file=str(secret_file),
    )

    assert settings.database_url.startswith(
        "postgresql+asyncpg://runtime:"
    )


def test_production_rejects_database_credentials_in_environment(
    tmp_path,
    monkeypatch,
) -> None:
    secret_file = tmp_path / "runtime-database-url"
    secret_file.write_text(
        "postgresql+asyncpg://runtime:test@postgres:5432/opex",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "OPEX_DATABASE_URL",
        "postgresql+asyncpg://forbidden:test@postgres:5432/opex",
    )
    monkeypatch.delenv("OPEX_MIGRATION_DATABASE_URL", raising=False)

    with pytest.raises(
        ValueError,
        match="must not be supplied through environment",
    ):
        Settings(
            environment="production",
            auth_mode="oidc",
            oidc_issuer="https://identity.example.com",
            oidc_audience="opex-core-api",
            oidc_jwks_url="https://identity.example.com/.well-known/jwks.json",
            allowed_hosts="app.example.com",
            cors_origins="https://app.example.com",
            database_url_file=str(secret_file),
        )



@pytest.mark.asyncio
async def test_database_permissions_are_authoritative_and_fail_closed(
    monkeypatch,
) -> None:
    async def fake_resolve_principal_access(**kwargs):
        return {
            "tenant_status": "active",
            "membership_id": (
                "00000000-0000-0000-0000-000000000099"
            ),
            "membership_status": "active",
            "roles": ("viewer",),
            "permission_assignments": (
                {
                    "key": "module:admin_access:view",
                    "role_key": "viewer",
                    "scope": {
                        "warehouses": ["wh-1"],
                    },
                },
                {
                    "key": "module:admin_access:view",
                    "role_key": "operator",
                    "scope": {
                        "warehouses": ["wh-2"],
                    },
                },
                {
                    "key": "module:not_a_real_module:view",
                    "role_key": "viewer",
                    "scope": {},
                },
                {
                    "key": "module:admin_access:view",
                    "role_key": "viewer",
                    "scope": "not-a-dict",
                },
            ),
        }

    monkeypatch.setattr(
        security,
        "resolve_principal_access",
        fake_resolve_principal_access,
    )

    # Hostile token claims super_admin. DB says viewer.
    principal = await get_current_principal(
        make_request(),
        make_credentials(
            "forged-user",
            "super_admin",
        ),
        Settings(
            environment="development",
            auth_mode="development",
        ),
    )

    assert principal.roles == ("viewer",)
    assert "super_admin" not in principal.roles

    # Only the known DB permission survives.
    assert principal.permissions == (
        "module:admin_access:view",
    )

    # Unknown permission and malformed scope are fail-closed.
    assert len(principal.permission_assignments) == 2

    assignments = {
        (
            item.role_key,
            tuple(item.scope.get("warehouses", [])),
        )
        for item in principal.permission_assignments
    }

    assert assignments == {
        ("viewer", ("wh-1",)),
        ("operator", ("wh-2",)),
    }


@pytest.mark.asyncio
async def test_context_returns_only_db_authoritative_permissions(
    monkeypatch,
) -> None:
    async def fake_resolve_principal_access(**kwargs):
        return {
            "tenant_status": "active",
            "membership_id": (
                "00000000-0000-0000-0000-000000000099"
            ),
            "membership_status": "active",
            "roles": ("viewer",),
            "permission_assignments": (
                {
                    "key": "module:admin_access:view",
                    "role_key": "viewer",
                    "scope": {
                        "warehouses": ["wh-1"],
                    },
                },
                {
                    "key": "totally:unknown:permission",
                    "role_key": "viewer",
                    "scope": {},
                },
            ),
        }

    monkeypatch.setattr(
        security,
        "resolve_principal_access",
        fake_resolve_principal_access,
    )

    request = make_request()
    request.state.request_id = "permission-context-test"

    principal = await get_current_principal(
        request,
        make_credentials(
            "context-user",
            "super_admin",
        ),
        Settings(
            environment="development",
            auth_mode="development",
        ),
    )

    # Import locally so this remains an authorization-focused test.
    from app.main import current_context

    payload = await current_context(
        request=request,
        principal=principal,
    )

    assert payload["roles"] == ("viewer",)

    assert payload["permissions"] == (
        "module:admin_access:view",
    )

    assert payload["permission_assignments"] == [
        {
            "key": "module:admin_access:view",
            "role_key": "viewer",
            "scope": {
                "warehouses": ["wh-1"],
            },
        }
    ]

    assert "totally:unknown:permission" not in str(payload)


def test_principal_starts_without_token_permissions() -> None:
    principal = security._decode_development_token(
        f"dev.user-1.{TENANT_ID}.super_admin"
    )

    # Authentication token may provide an initial role claim in
    # development mode, but it can never manufacture application
    # permissions. Those only arrive from DB authorization.
    assert principal.permissions == ()
    assert principal.permission_assignments == ()
