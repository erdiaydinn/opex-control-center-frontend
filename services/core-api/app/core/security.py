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
from app.core.internal_identity import (
    InternalAssertionInvalid,
    InternalAssertionUnavailable,
    VerifiedInternalService,
    verify_internal_service_assertion,
)
from app.core.internal_service_replay import (
    INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS,
    InternalServiceReplayDetected,
    InternalServiceReplayUnavailable,
    RedisInternalServiceReplayGuard,
)
from app.core.permission_catalog import is_known_permission
from app.core.resources import redis_client, resolve_principal_access

bearer_scheme = HTTPBearer(auto_error=False)

_internal_service_replay_guard = (
    RedisInternalServiceReplayGuard(
        redis_client
    )
)

INTERNAL_SERVICE_ASSERTION_HEADER = (
    "X-OPEX-Internal-Service-Assertion"
)
AUTHORIZATION_HEADER = "Authorization"
MAX_BEARER_TOKEN_CHARACTERS = 16384


def _internal_service_authentication_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Internal service authentication failed",
    )


def _bearer_authentication_failed(
    detail: str = "Invalid bearer access token",
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _validated_bearer_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    """Return one unambiguous Bearer token or fail closed.

    HTTPBearer remains attached for OpenAPI/dependency compatibility, but raw
    ASGI headers are the trust boundary. This prevents duplicate Authorization
    fields, proxy-coalesced credentials, whitespace/control-character
    ambiguity, and parser disagreement from silently selecting one credential.
    """

    header_values = request.headers.getlist(
        AUTHORIZATION_HEADER
    )

    if header_values:
        if len(header_values) != 1:
            raise _bearer_authentication_failed()

        raw_header = header_values[0]

        if (
            not raw_header
            or len(raw_header) > (
                MAX_BEARER_TOKEN_CHARACTERS
                + len("Bearer ")
            )
            or raw_header != raw_header.strip()
            or "," in raw_header
            or "\t" in raw_header
        ):
            raise _bearer_authentication_failed()

        scheme, separator, token = raw_header.partition(" ")

        if (
            separator != " "
            or scheme.lower() != "bearer"
            or not token
            or len(token) > MAX_BEARER_TOKEN_CHARACTERS
            or token != token.strip()
            or any(
                ord(character) < 33
                or ord(character) == 127
                for character in token
            )
        ):
            raise _bearer_authentication_failed()

        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or credentials.credentials != token
        ):
            raise _bearer_authentication_failed()

        return token

    # Direct in-process/unit invocation may supply the FastAPI dependency value
    # without an ASGI header. Production HTTP cannot produce credentials here
    # without an Authorization header, so this keeps existing unit ergonomics
    # without relaxing the network trust boundary above.
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
    ):
        raise _bearer_authentication_failed(
            "Bearer access token is required"
        )

    token = credentials.credentials

    if (
        not token
        or len(token) > MAX_BEARER_TOKEN_CHARACTERS
        or token != token.strip()
        or "," in token
        or any(
            ord(character) < 33
            or ord(character) == 127
            for character in token
        )
    ):
        raise _bearer_authentication_failed()

    return token


async def require_internal_service(
    request: Request,
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
) -> VerifiedInternalService:
    """
    Authenticate OPEX service-to-service pre-auth calls.

    This deliberately does not consume Authorization/Bearer.
    """

    header_values = request.headers.getlist(
        INTERNAL_SERVICE_ASSERTION_HEADER
    )

    # Fail closed for:
    # - missing header
    # - duplicate ASGI header fields
    #
    # A reverse proxy can also coalesce duplicate fields into
    # one comma-separated field, handled below.
    if len(header_values) != 1:
        raise (
            _internal_service_authentication_failed()
        )

    token = header_values[0]

    if (
        not token
        or len(token) > 8192
        or token != token.strip()
        or "," in token
        or any(
            character.isspace()
            for character in token
        )
    ):
        raise (
            _internal_service_authentication_failed()
        )

    try:
        verified = (
            verify_internal_service_assertion(
                token,
                settings,
            )
        )

    except InternalAssertionInvalid as exc:
        # Never expose verifier internals as an authentication
        # oracle to an untrusted caller.
        raise (
            _internal_service_authentication_failed()
        ) from exc

    except InternalAssertionUnavailable as exc:
        # Trusted key material/configuration being unavailable
        # is an infrastructure failure, not an auth bypass.
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Internal service authentication unavailable"
            ),
        ) from exc

    request.state.internal_service = verified

    return verified


async def require_fresh_internal_service(
    request: Request,
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
) -> VerifiedInternalService:
    """
    Require a cryptographically valid AND single-use
    Identity Gateway service assertion.
    """

    verified = await require_internal_service(
        request,
        settings,
    )

    # Verified service assertions are already bounded to
    # settings.internal_assertion_max_lifetime_seconds.
    #
    # Keep the replay tombstone slightly longer than the
    # maximum acceptance window, including verifier clock skew.
    ttl_seconds = (
        settings.
        internal_assertion_max_lifetime_seconds
        + INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS
    )

    try:
        await (
            _internal_service_replay_guard.consume(
                assertion_id=(
                    verified.assertion_id
                ),
                ttl_seconds=ttl_seconds,
            )
        )

    except InternalServiceReplayDetected as exc:
        # A rejected replay must never remain represented as an
        # authenticated service on request state.
        request.state.internal_service = None

        # Deliberately indistinguishable from all other
        # authentication failures.
        raise (
            _internal_service_authentication_failed()
        ) from exc

    except InternalServiceReplayUnavailable as exc:
        request.state.internal_service = None

        # Redis is part of the authentication authority here.
        # Never degrade to "accept without replay checking".
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Internal service authentication unavailable"
            ),
        ) from exc

    return verified


class PermissionAssignment(BaseModel):
    key: str
    role_key: str
    scope: dict[str, Any]


class Principal(BaseModel):
    subject: str
    tenant_id: UUID
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    permission_assignments: tuple[PermissionAssignment, ...] = ()
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
        header = jwt.get_unverified_header(token)
        algorithm = str(header.get("alg", "")).strip()

        if algorithm not in settings.oidc_algorithm_list:
            raise jwt.InvalidAlgorithmError("Token signing algorithm is not allowed")

        client = get_jwk_client(settings.oidc_jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.oidc_algorithm_list,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            leeway=30,
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
    token = _validated_bearer_token(
        request,
        credentials,
    )

    if settings.auth_mode == "development":
        principal = _decode_development_token(token)
    else:
        principal = await _decode_oidc_token(token, settings)

    # Authentication succeeded. Keep the verified identity for audit only.
    # This does not mean the principal is authorized for tenant access.
    request.state.authenticated_principal = principal

    try:
        access = await resolve_principal_access(
            tenant_id=str(principal.tenant_id),
            subject=principal.subject,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authorization service is unavailable",
        ) from exc

    if (
        access is None
        or access["tenant_status"] != "active"
        or access["membership_status"] != "active"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Principal has no active tenant access",
        )

    permission_assignments: list[PermissionAssignment] = []

    for item in access["permission_assignments"]:
        if not isinstance(item, dict):
            continue

        permission_key = str(
            item.get("key", "")
        ).strip()

        role_key = str(
            item.get("role_key", "")
        ).strip()

        scope = item.get("scope")

        if (
            not permission_key
            or not role_key
            or not is_known_permission(permission_key)
            or not isinstance(scope, dict)
        ):
            continue

        permission_assignments.append(
            PermissionAssignment(
                key=permission_key,
                role_key=role_key,
                scope=scope,
            )
        )

    permission_assignments.sort(
        key=lambda item: (
            item.key,
            item.role_key,
            repr(sorted(item.scope.items())),
        )
    )

    principal = principal.model_copy(
        update={
            "roles": tuple(
                sorted(
                    {
                        str(role)
                        for role in access["roles"]
                        if str(role).strip()
                    }
                )
            ),
            "permissions": tuple(
                sorted(
                    {
                        item.key
                        for item in permission_assignments
                    }
                )
            ),
            "permission_assignments": tuple(
                permission_assignments
            ),
        }
    )

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


require_super_admin = require_roles(
    ROLE_SUPER_ADMIN,
)

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
