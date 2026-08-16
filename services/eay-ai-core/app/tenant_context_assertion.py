"""Fail-closed verification for canonical tenant context entering EAY AI Core.

This verifier deliberately uses a dedicated JWT type and audience. Existing Core API
end-user assertions MUST NOT be forwarded to AI Core as tenant authority.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import jwt

TENANT_CONTEXT_TYP = "eay-ai-tenant-context+jwt"
TENANT_CONTEXT_PURPOSE = "grounded-retrieval"
MAX_JWKS_BYTES = 256 * 1024
MAX_JWKS_KEYS = 16
KID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
JTI_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
PRIVATE_JWK_FIELDS = {"d", "p", "q", "dp", "dq", "qi", "oth", "k"}
ALLOWED_CLAIMS = {
    "iss",
    "aud",
    "sub",
    "tenant_id",
    "membership_id",
    "purpose",
    "jti",
    "iat",
    "nbf",
    "exp",
}


class TenantContextAssertionInvalid(ValueError):
    """The presented assertion is untrusted or violates the contract."""


class TenantContextAssertionUnavailable(RuntimeError):
    """Trusted verification material/configuration is unavailable."""


@dataclass(frozen=True)
class VerifiedTenantContext:
    tenant_id: UUID
    membership_id: UUID
    actor_subject: str
    assertion_id: str


def _load_public_jwks(path_value: str) -> tuple[dict[str, object], ...]:
    path = Path(path_value)
    try:
        stat = path.stat()
    except OSError as exc:
        raise TenantContextAssertionUnavailable("tenant-context JWKS unavailable") from exc
    if not path.is_file() or stat.st_size <= 0 or stat.st_size > MAX_JWKS_BYTES:
        raise TenantContextAssertionUnavailable("tenant-context JWKS invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TenantContextAssertionUnavailable("tenant-context JWKS unreadable") from exc
    keys = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(keys, list) or not keys or len(keys) > MAX_JWKS_KEYS:
        raise TenantContextAssertionUnavailable("tenant-context JWKS key set invalid")

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in keys:
        if not isinstance(item, dict):
            raise TenantContextAssertionUnavailable("tenant-context JWK invalid")
        kid = item.get("kid")
        if not isinstance(kid, str) or not KID_PATTERN.fullmatch(kid) or kid in seen:
            raise TenantContextAssertionUnavailable("tenant-context JWK kid invalid")
        if PRIVATE_JWK_FIELDS.intersection(item):
            raise TenantContextAssertionUnavailable("private key material forbidden in AI Core JWKS")
        if item.get("kty") != "EC" or item.get("crv") != "P-256":
            raise TenantContextAssertionUnavailable("tenant-context JWK must be P-256 EC")
        if item.get("use") not in {None, "sig"} or item.get("alg") not in {None, "ES256"}:
            raise TenantContextAssertionUnavailable("tenant-context JWK metadata invalid")
        seen.add(kid)
        normalized.append(item)
    return tuple(normalized)


def verify_tenant_context_assertion(
    token: str,
    *,
    jwks_file: str,
    issuer: str,
    audience: str,
    max_lifetime_seconds: int = 60,
) -> VerifiedTenantContext:
    if not token or len(token) > 8192 or not issuer or not audience:
        raise TenantContextAssertionInvalid("tenant-context assertion invalid")
    if audience == "opex-core-api":
        raise TenantContextAssertionInvalid("AI Core audience must be distinct from Core API")
    if max_lifetime_seconds < 1 or max_lifetime_seconds > 60:
        raise TenantContextAssertionInvalid("tenant-context lifetime policy invalid")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TenantContextAssertionInvalid("tenant-context header invalid") from exc
    if set(header) != {"alg", "kid", "typ"}:
        raise TenantContextAssertionInvalid("tenant-context header contract invalid")
    if header.get("alg") != "ES256" or header.get("typ") != TENANT_CONTEXT_TYP:
        raise TenantContextAssertionInvalid("tenant-context algorithm/type invalid")
    kid = header.get("kid")
    if not isinstance(kid, str) or not KID_PATTERN.fullmatch(kid):
        raise TenantContextAssertionInvalid("tenant-context kid invalid")

    matches = [item for item in _load_public_jwks(jwks_file) if item.get("kid") == kid]
    if len(matches) != 1:
        raise TenantContextAssertionInvalid("tenant-context signing key not trusted")
    try:
        verification_key = jwt.PyJWK.from_dict(matches[0]).key
        claims = jwt.decode(
            token,
            verification_key,
            algorithms=["ES256"],
            audience=audience,
            issuer=issuer,
            leeway=5,
            options={
                "require": [
                    "iss", "aud", "sub", "tenant_id", "membership_id",
                    "purpose", "jti", "iat", "nbf", "exp",
                ]
            },
        )
    except jwt.PyJWTError as exc:
        raise TenantContextAssertionInvalid("tenant-context signature/claims invalid") from exc

    if set(claims) != ALLOWED_CLAIMS:
        raise TenantContextAssertionInvalid("unexpected tenant-context claims")
    if claims.get("purpose") != TENANT_CONTEXT_PURPOSE:
        raise TenantContextAssertionInvalid("tenant-context purpose invalid")
    actor_subject = claims.get("sub")
    if not isinstance(actor_subject, str) or not actor_subject.strip() or len(actor_subject) > 255:
        raise TenantContextAssertionInvalid("tenant-context actor invalid")
    try:
        tenant_id = UUID(str(claims["tenant_id"]))
        membership_id = UUID(str(claims["membership_id"]))
    except (TypeError, ValueError) as exc:
        raise TenantContextAssertionInvalid("tenant-context identity invalid") from exc
    assertion_id = claims.get("jti")
    if not isinstance(assertion_id, str) or not JTI_PATTERN.fullmatch(assertion_id):
        raise TenantContextAssertionInvalid("tenant-context assertion id invalid")

    for name in ("iat", "nbf", "exp"):
        value = claims[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TenantContextAssertionInvalid("tenant-context timestamps invalid")
    issued_at = float(claims["iat"])
    if float(claims["nbf"]) != issued_at:
        raise TenantContextAssertionInvalid("tenant-context nbf must equal iat")
    lifetime = float(claims["exp"]) - issued_at
    if lifetime <= 0 or lifetime > max_lifetime_seconds or issued_at > time.time() + 5:
        raise TenantContextAssertionInvalid("tenant-context lifetime invalid")

    return VerifiedTenantContext(
        tenant_id=tenant_id,
        membership_id=membership_id,
        actor_subject=actor_subject.strip(),
        assertion_id=assertion_id,
    )
