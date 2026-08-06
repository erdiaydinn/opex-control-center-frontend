from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

import anyio
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel

from app.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    subject: str
    tenant_id: UUID
    roles: tuple[str, ...] = ()
    auth_mode: str


@lru_cache
def get_jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True)


def _normalize_roles(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(role.strip() for role in value.split(",") if role.strip())
    if isinstance(value, list):
        return tuple(str(role).strip() for role in value if str(role).strip())
    return ()


def _require_tenant_uuid(value: Any, *, invalid_status: int) -> UUID:
    try:
        return UUID(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=invalid_status,
            detail="Token has no valid tenant context",
        ) from exc


def _decode_development_token(token: str) -> Principal:
    # Local-only format: dev.<subject>.<tenant_uuid>.<comma-separated-roles>
    parts = token.split(".", maxsplit=3)
    if len(parts) != 4 or parts[0] != "dev":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid development token",
        )

    _, subject, tenant_id, roles = parts
    if not subject or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Development token requires subject and tenant",
        )

    return Principal(
        subject=subject,
        tenant_id=_require_tenant_uuid(
            tenant_id,
            invalid_status=status.HTTP_401_UNAUTHORIZED,
        ),
        roles=_normalize_roles(roles),
        auth_mode="development",
    )


async def _decode_oidc_token(token: str, settings: Settings) -> Principal:
    def decode() -> dict[str, Any]:
        client = get_jwk_client(settings.oidc_jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.oidc_algorithm_list,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )

    try:
        claims = await anyio.to_thread.run_sync(decode)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider verification is unavailable",
        ) from exc

    return Principal(
        subject=str(claims["sub"]),
        tenant_id=_require_tenant_uuid(
            claims.get(settings.oidc_tenant_claim),
            invalid_status=status.HTTP_403_FORBIDDEN,
        ),
        roles=_normalize_roles(claims.get(settings.oidc_roles_claim)),
        auth_mode="oidc",
    )


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if settings.auth_mode == "development":
        principal = _decode_development_token(credentials.credentials)
    else:
        principal = await _decode_oidc_token(credentials.credentials, settings)

    request.state.principal = principal
    request.state.tenant_id = principal.tenant_id
    return principal


ROLE_SUPER_ADMIN = "super_admin"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"

ROLE_ALIASES = {
    "super_admins": ROLE_SUPER_ADMIN,
    "platform_admins": ROLE_PLATFORM_ADMIN,
    "operators": ROLE_OPERATOR,
    "viewers": ROLE_VIEWER,
}


def normalize_principal_roles(principal: Principal) -> set[str]:
    roles: set[str] = set()

    for role in principal.roles:
        normalized = role.strip().lower()
        roles.add(ROLE_ALIASES.get(normalized, normalized))

    return roles


def require_roles(*allowed_roles: str):
    normalized_allowed = {
        ROLE_ALIASES.get(role.strip().lower(), role.strip().lower())
        for role in allowed_roles
    }

    async def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        principal_roles = normalize_principal_roles(principal)

        if ROLE_SUPER_ADMIN in principal_roles:
            return principal

        if principal_roles.isdisjoint(normalized_allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "You do not have permission to perform this action",
                    "required_roles": sorted(normalized_allowed),
                },
            )

        return principal

    return dependency


require_platform_admin = require_roles(
    ROLE_SUPER_ADMIN,
    ROLE_PLATFORM_ADMIN,
)

require_operator = require_roles(
    ROLE_SUPER_ADMIN,
    ROLE_PLATFORM_ADMIN,
    ROLE_OPERATOR,
)

require_viewer = require_roles(
    ROLE_SUPER_ADMIN,
    ROLE_PLATFORM_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
)
