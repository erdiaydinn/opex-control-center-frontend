"""OIDC/JWT authentication boundary for OPEX APIs.

Identity headers are generated here after signature validation. Client supplied
role/permission headers are removed in production and never treated as proof of
identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant_id: str
    email: str
    name: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    employee_id: str | None = None
    warehouse_scope: tuple[str, ...] = ()
    force_password_change: bool = False

    @property
    def primary_role(self) -> str:
        for role in self.roles:
            if str(role).lower().replace("-", "_") in {
                "super_admin", "superadmin", "admin", "administrator", "hr",
                "warehouse_manager", "manager", "regional_executive",
                "regional_manager", "by",
            }:
                return str(role)
        return self.roles[0] if self.roles else "viewer"


def _items(claims: dict[str, Any], key: str) -> tuple[str, ...]:
    value = claims.get(key, [])
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    return tuple(str(item) for item in value if str(item).strip())


def _decode_bearer(token: str) -> dict[str, Any]:
    import jwt

    issuer = os.getenv("OPEX_OIDC_ISSUER", "").rstrip("/")
    audience = os.getenv("OPEX_OIDC_AUDIENCE", "")
    if not issuer and os.getenv("OPEX_LOCAL_AUTH_ENABLED", "true").lower() == "true":
        from app.modules.identity.service import IdentityRuleError, validate_local_claims
        try:
            secret = os.environ["OPEX_LOCAL_JWT_SECRET"]
            claims = jwt.decode(
                token, secret, algorithms=["HS256"], issuer="opex-local",
                audience="opex-control-center", options={"require": ["exp", "iat", "sub"]}, leeway=15,
            )
            return validate_local_claims(claims)
        except (KeyError, IdentityRuleError, jwt.PyJWTError) as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Yerel oturum geçersiz veya iptal edilmiş.") from error
    jwks_url = os.getenv("OPEX_OIDC_JWKS_URL", f"{issuer}/.well-known/jwks.json")
    if not issuer or not audience:
        raise HTTPException(status_code=503, detail="Kurumsal kimlik sağlayıcısı yapılandırılmamış.")
    try:
        signing_key = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=os.getenv("OPEX_OIDC_ALGORITHMS", "RS256").split(","),
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "iat", "sub"]},
            leeway=30,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SSO oturumu geçersiz veya süresi dolmuş.") from error


def identity_from_request(request: Request) -> Identity:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        claims = _decode_bearer(authorization.split(" ", 1)[1].strip())
        role_claim = os.getenv("OPEX_OIDC_ROLES_CLAIM", "roles")
        permission_claim = os.getenv("OPEX_OIDC_PERMISSIONS_CLAIM", "permissions")
        employee_id_claim = os.getenv("OPEX_OIDC_EMPLOYEE_ID_CLAIM", "employee_id")
        return Identity(
            subject=str(claims["sub"]),
            tenant_id=str(claims.get(os.getenv("OPEX_OIDC_TENANT_ID_CLAIM", "tenant_id"), "")),
            email=str(claims.get("email", "")),
            name=str(claims.get("name") or claims.get("preferred_username") or claims["sub"]),
            roles=_items(claims, role_claim),
            permissions=_items(claims, permission_claim),
            employee_id=str(claims.get(employee_id_claim)) if claims.get(employee_id_claim) else None,
            warehouse_scope=_items(claims, os.getenv("OPEX_OIDC_WAREHOUSE_SCOPE_CLAIM", "warehouse_scope")),
            force_password_change=bool(claims.get("force_password_change", False)),
        )

    environment = os.getenv("DOCKOS_ENV", "development").lower()
    allow_legacy = os.getenv("OPEX_ALLOW_LEGACY_HEADERS", "true" if environment != "production" else "false").lower() == "true"
    if allow_legacy:
        permissions = tuple(filter(None, request.headers.get("x-opex-permissions", "").split(",")))
        user = request.headers.get("x-opex-user", "development-user")
        return Identity(
            user,
            os.getenv("OPEX_DEVELOPMENT_TENANT_ID", "eay-development"),
            user,
            user,
            (request.headers.get("x-opex-role", "super_admin"),),
            permissions,
        )
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kurumsal SSO oturumu gerekli.")


PUBLIC_PATHS = {
    "/health", "/api/workforce/health", "/api/recruitment/health", "/api/dockos/health",
    "/api/inventory/health", "/api/identity/login", "/api/identity/refresh",
}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path == "/api/recruitment/candidate-upload/evidence"


class WorkforceIdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        protected_prefix = any(request.url.path.startswith(prefix) for prefix in (
            "/api/workforce", "/api/recruitment", "/api/inventory", "/api/identity",
        ))
        if protected_prefix and not _is_public_path(request.url.path):
            try:
                identity = identity_from_request(request)
            except HTTPException as error:
                from fastapi.responses import JSONResponse

                return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
            request.state.identity = identity
            if identity.force_password_change and request.url.path != "/api/identity/password/change":
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Devam etmeden önce geçici parolanızı değiştirin."},
                )
            # Headers passed to route handlers are derived from verified claims.
            headers = [(key, value) for key, value in request.scope["headers"] if key not in {b"x-opex-user", b"x-opex-role", b"x-opex-permissions"}]
            headers.extend(
                [
                    (b"x-opex-user", identity.subject.encode()),
                    (b"x-opex-role", identity.primary_role.encode()),
                    (b"x-opex-permissions", ",".join(identity.permissions).encode()),
                ]
            )
            request.scope["headers"] = headers
        return await call_next(request)


def mask_tckn(value: str | None, can_view: bool) -> str | None:
    if not value:
        return value
    digits = "".join(character for character in str(value) if character.isdigit())
    return digits if can_view else (f"{digits[:2]}*******{digits[-2:]}" if len(digits) >= 4 else "****")
