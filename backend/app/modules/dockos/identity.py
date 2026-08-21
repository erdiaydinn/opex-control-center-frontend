from __future__ import annotations

import hashlib
import hmac
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request
from .tenant_db import consume_gateway_replay


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    role: str
    tenant_key: str


_CURRENT_IDENTITY: ContextVar[Identity | None] = ContextVar("dockos_identity", default=None)
_JWKS_CLIENT = None


def current_identity() -> Identity | None:
    return _CURRENT_IDENTITY.get()


def set_identity(identity: Identity):
    return _CURRENT_IDENTITY.set(identity)


def reset_identity(token):
    _CURRENT_IDENTITY.reset(token)


def _production() -> bool:
    return os.getenv("DOCKOS_ENV", "development").lower() == "production"


def _roles(claims: dict) -> list[str]:
    claim_name = os.getenv("DOCKOS_OIDC_ROLES_CLAIM", "roles")
    value = claims.get(claim_name, [])
    if isinstance(value, str):
        return [part.strip() for part in value.replace(",", " ").split() if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _role_from_claims(claims: dict) -> str:
    roles = {item.casefold() for item in _roles(claims)}
    admin_roles = {
        item.strip().casefold()
        for item in os.getenv("DOCKOS_ADMIN_ROLES", "dockos_admin,opex_admin").split(",")
        if item.strip()
    }
    return "dockos_admin" if roles & admin_roles else "supplier"


def _verify_oidc_token(token: str) -> Identity:
    global _JWKS_CLIENT
    issuer = os.getenv("DOCKOS_OIDC_ISSUER", "").rstrip("/")
    audience = os.getenv("DOCKOS_OIDC_AUDIENCE", "")
    jwks_url = os.getenv("DOCKOS_OIDC_JWKS_URL", "")
    if not issuer or not audience or not jwks_url:
        raise HTTPException(503, "DockOS kurumsal SSO yapılandırması eksik.")
    if _JWKS_CLIENT is None:
        _JWKS_CLIENT = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300)
    try:
        signing_key = _JWKS_CLIENT.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
            leeway=30,
        )
    except Exception as error:
        raise HTTPException(401, "DockOS SSO token doğrulaması başarısız.") from error

    email_claim = os.getenv("DOCKOS_OIDC_EMAIL_CLAIM", "email")
    email = str(claims.get(email_claim) or "").strip().lower()
    subject = str(claims.get("sub") or "").strip()
    if not subject or "@" not in email:
        raise HTTPException(401, "DockOS SSO kimliğinde subject/e-posta eksik.")

    configured_tenant = os.getenv("DOCKOS_TENANT_KEY", "ys_tr").strip().lower()
    tenant_claim_name = os.getenv("DOCKOS_OIDC_TENANT_CLAIM", "")
    token_tenant = str(claims.get(tenant_claim_name) or configured_tenant).strip().lower() if tenant_claim_name else configured_tenant
    if token_tenant != configured_tenant:
        raise HTTPException(403, "DockOS tenant eşleşmesi başarısız.")
    return Identity(subject=subject, email=email, role=_role_from_claims(claims), tenant_key=configured_tenant)


def authenticate_request(request: Request) -> Identity:
    if not _production():
        email = (request.headers.get("X-OPEX-User") or "erdi.aydin@yemeksepeti.com").strip().lower()
        role = (request.headers.get("X-OPEX-Role") or "admin").strip().lower()
        return Identity(subject=email, email=email, role=role, tenant_key=os.getenv("DOCKOS_TENANT_KEY", "ys_tr"))
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Kurumsal SSO Bearer token zorunludur.")
    return _verify_oidc_token(authorization[7:].strip())


def _gateway_secrets():
    values = [os.getenv("DOCKOS_GATEWAY_SECRET", ""), os.getenv("DOCKOS_GATEWAY_PREVIOUS_SECRET", "")]
    return [value for value in values if len(value) >= 32 and not value.startswith("CHANGE_ME")]


def verify_gateway(request: Request) -> None:
    if not _production() or request.url.path.endswith("/health") or request.url.path.endswith("/readiness"):
        return
    secrets = _gateway_secrets()
    if not secrets:
        raise HTTPException(503, "DockOS gateway secret production için geçersiz.")
    mode = os.getenv("DOCKOS_GATEWAY_TRUST_MODE", "hmac").lower()
    if mode != "hmac":
        raise HTTPException(503, "Production gateway trust mode hmac olmalıdır.")
    timestamp = request.headers.get("X-DockOS-Gateway-Timestamp", "")
    nonce = request.headers.get("X-DockOS-Gateway-Nonce", "").strip()
    signature = request.headers.get("X-DockOS-Gateway-Signature", "")
    if len(nonce) < 16:
        raise HTTPException(401, "Gateway nonce eksik veya geçersiz.")
    try:
        ts = int(timestamp)
    except ValueError as error:
        raise HTTPException(401, "Gateway timestamp geçersiz.") from error
    max_skew = max(10, int(os.getenv("DOCKOS_GATEWAY_MAX_SKEW_SECONDS", "60")))
    if abs(int(time.time()) - ts) > max_skew:
        raise HTTPException(401, "Gateway isteği zaman penceresi dışında.")
    auth_hash = hashlib.sha256(request.headers.get("Authorization", "").encode("utf-8")).hexdigest()
    canonical = f"{timestamp}\n{nonce}\n{request.method.upper()}\n{request.url.path}\n{auth_hash}".encode("utf-8")
    valid = any(hmac.compare_digest(hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest(), signature) for secret in secrets)
    if not valid:
        raise HTTPException(401, "DockOS production gateway imzası doğrulanamadı.")
    try:
        consumed = consume_gateway_replay(timestamp, nonce, signature, max_skew)
    except Exception as error:
        raise HTTPException(503, "Gateway replay doğrulama deposuna ulaşılamadı.") from error
    if not consumed:
        raise HTTPException(401, "Gateway replay isteği reddedildi.")
