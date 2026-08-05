import pytest

from app.core.config import Settings
from app.core.security import _decode_development_token


def test_production_rejects_development_auth() -> None:
    with pytest.raises(ValueError, match="Production requires"):
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


def test_development_token_carries_tenant_context() -> None:
    principal = _decode_development_token("dev.user-1.tenant-a.inventory_admin,viewer")

    assert principal.subject == "user-1"
    assert principal.tenant_id == "tenant-a"
    assert principal.roles == ("inventory_admin", "viewer")


def test_development_token_rejects_missing_tenant() -> None:
    with pytest.raises(Exception):
        _decode_development_token("dev.user-1..viewer")
