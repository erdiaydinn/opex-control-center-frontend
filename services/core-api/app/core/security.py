from functools import lru_cache
from typing import Annotated, Any

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
    tenant_id: str
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


def _decode_development_token(token: str) -> Principal:
    # Local-only format: dev.<subject>.<tenant_id>.<comma-separated-roles>
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
        tenant_id=tenant_id,
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

    tenant_id = str(claims.get(settings.oidc_tenant_claim, "")).strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token has no tenant context",
        )

    return Principal(
        subject=str(claims["sub"]),
        tenant_id=tenant_id,
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
