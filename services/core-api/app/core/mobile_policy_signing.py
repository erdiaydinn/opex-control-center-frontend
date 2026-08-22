"""Asymmetric integrity envelope for short-lived EAY Mobile policy snapshots.

Signed policy is an edge-cache integrity mechanism, never a replacement for
canonical backend authorization. Production private keys belong in a KMS/HSM
signing provider; no shared verification secret is embedded in an APK.
"""

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import jwt
from pydantic import BaseModel, Field, ValidationError

from app.core.mobile_policy import (
    MobileOperationPolicy,
    MobilePolicySnapshot,
    MobileRuntimeProfile,
)

MOBILE_POLICY_ALGORITHM = "ES256"
MOBILE_POLICY_AUDIENCE = "eay-mobile-edge"
MOBILE_POLICY_ISSUER = "eay-platform-core"
MOBILE_POLICY_TOKEN_TYPE = "EAY-MOBILE-POLICY+JWT"
MOBILE_POLICY_VERSION = 1
MAX_SIGNED_POLICY_LIFETIME_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 5


class MobilePolicyTokenError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MobilePolicySigningProvider(Protocol):
    """External signer boundary. Production implementation should be KMS/HSM backed."""

    @property
    def kid(self) -> str:
        ...

    @property
    def algorithm(self) -> str:
        ...

    def sign(
        self,
        claims: dict[str, Any],
        headers: dict[str, str],
    ) -> str:
        ...


class MobilePolicyBinding(BaseModel):
    tenant_id: UUID
    actor_id: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=128)
    installation_id: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=128)
    auth_binding_id: str = Field(min_length=1, max_length=128)
    runtime_profile: MobileRuntimeProfile


class SignedMobilePolicyClaims(BaseModel):
    iss: str
    aud: str
    sub: str
    typ: str
    ver: int
    tenant_id: UUID
    device_id: str
    installation_id: str
    location_id: str
    auth_binding_id: str
    runtime_profile: MobileRuntimeProfile
    policy_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation_policies: dict[str, MobileOperationPolicy]
    iat: int
    nbf: int
    exp: int
    jti: str = Field(pattern=r"^[a-f0-9]{64}$")

    def binding(self) -> MobilePolicyBinding:
        return MobilePolicyBinding(
            tenant_id=self.tenant_id,
            actor_id=self.sub,
            device_id=self.device_id,
            installation_id=self.installation_id,
            location_id=self.location_id,
            auth_binding_id=self.auth_binding_id,
            runtime_profile=self.runtime_profile,
        )


def _epoch(value: datetime) -> int:
    if value.tzinfo is None:
        raise MobilePolicyTokenError("DENY_POLICY_TIMEZONE")
    return int(value.astimezone(UTC).timestamp())


def _jti(
    *,
    policy_fingerprint: str,
    tenant_id: UUID,
    actor_id: str,
    device_id: str,
    installation_id: str,
    auth_binding_id: str,
    issued_at: int,
    expires_at: int,
) -> str:
    material = "|".join(
        (
            policy_fingerprint,
            str(tenant_id),
            actor_id,
            device_id,
            installation_id,
            auth_binding_id,
            str(issued_at),
            str(expires_at),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_signed_policy_claims(
    snapshot: MobilePolicySnapshot,
) -> dict[str, Any]:
    issued_at = _epoch(snapshot.issued_at)
    expires_at = _epoch(snapshot.expires_at)
    lifetime = expires_at - issued_at
    if lifetime <= 0 or lifetime > MAX_SIGNED_POLICY_LIFETIME_SECONDS:
        raise MobilePolicyTokenError("DENY_POLICY_LIFETIME")

    return {
        "iss": MOBILE_POLICY_ISSUER,
        "aud": MOBILE_POLICY_AUDIENCE,
        "sub": snapshot.actor_id,
        "typ": "mobile_policy",
        "ver": MOBILE_POLICY_VERSION,
        "tenant_id": str(snapshot.tenant_id),
        "device_id": snapshot.device_id,
        "installation_id": snapshot.installation_id,
        "location_id": snapshot.location_id,
        "auth_binding_id": snapshot.auth_binding_id,
        "runtime_profile": snapshot.runtime_profile.value,
        "policy_fingerprint": snapshot.policy_fingerprint,
        "operation_policies": {
            key: value.model_dump(mode="json")
            for key, value in sorted(snapshot.operation_policies.items())
        },
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "jti": _jti(
            policy_fingerprint=snapshot.policy_fingerprint,
            tenant_id=snapshot.tenant_id,
            actor_id=snapshot.actor_id,
            device_id=snapshot.device_id,
            installation_id=snapshot.installation_id,
            auth_binding_id=snapshot.auth_binding_id,
            issued_at=issued_at,
            expires_at=expires_at,
        ),
    }


def sign_mobile_policy(
    snapshot: MobilePolicySnapshot,
    signer: MobilePolicySigningProvider,
) -> str:
    if signer.algorithm != MOBILE_POLICY_ALGORITHM:
        raise MobilePolicyTokenError("DENY_SIGNER_ALGORITHM")
    kid = signer.kid.strip()
    if not kid or len(kid) > 128:
        raise MobilePolicyTokenError("DENY_SIGNER_KID")
    claims = build_signed_policy_claims(snapshot)
    return signer.sign(
        claims,
        {
            "alg": MOBILE_POLICY_ALGORITHM,
            "kid": kid,
            "typ": MOBILE_POLICY_TOKEN_TYPE,
        },
    )


def verify_mobile_policy(
    token: str,
    trusted_public_keys: Mapping[str, str | bytes],
    expected_binding: MobilePolicyBinding,
    *,
    now: datetime | None = None,
) -> SignedMobilePolicyClaims:
    if not token or len(token) > 32_768 or token != token.strip():
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_FORMAT")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_HEADER") from exc

    if header.get("alg") != MOBILE_POLICY_ALGORITHM:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_ALGORITHM")
    if header.get("typ") != MOBILE_POLICY_TOKEN_TYPE:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_TYPE")

    kid = str(header.get("kid", "")).strip()
    if not kid or len(kid) > 128 or kid not in trusted_public_keys:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_KID")

    try:
        raw_claims = jwt.decode(
            token,
            trusted_public_keys[kid],
            algorithms=[MOBILE_POLICY_ALGORITHM],
            issuer=MOBILE_POLICY_ISSUER,
            audience=MOBILE_POLICY_AUDIENCE,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "typ",
                    "ver",
                    "tenant_id",
                    "device_id",
                    "installation_id",
                    "location_id",
                    "auth_binding_id",
                    "runtime_profile",
                    "policy_fingerprint",
                    "operation_policies",
                    "iat",
                    "nbf",
                    "exp",
                    "jti",
                ],
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
        claims = SignedMobilePolicyClaims.model_validate(raw_claims)
    except (jwt.PyJWTError, ValidationError) as exc:
        raise MobilePolicyTokenError(
            "DENY_POLICY_TOKEN_SIGNATURE_OR_CLAIMS"
        ) from exc

    if claims.typ != "mobile_policy" or claims.ver != MOBILE_POLICY_VERSION:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_VERSION")

    current = _epoch(now or datetime.now(UTC))
    if claims.iat > current + MAX_CLOCK_SKEW_SECONDS:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_FUTURE")
    if claims.nbf > current + MAX_CLOCK_SKEW_SECONDS:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_NOT_YET_VALID")
    if claims.exp <= current:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_EXPIRED")
    lifetime = claims.exp - claims.iat
    if lifetime <= 0 or lifetime > MAX_SIGNED_POLICY_LIFETIME_SECONDS:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_LIFETIME")

    expected_jti = _jti(
        policy_fingerprint=claims.policy_fingerprint,
        tenant_id=claims.tenant_id,
        actor_id=claims.sub,
        device_id=claims.device_id,
        installation_id=claims.installation_id,
        auth_binding_id=claims.auth_binding_id,
        issued_at=claims.iat,
        expires_at=claims.exp,
    )
    if claims.jti != expected_jti:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_JTI")

    if claims.binding() != expected_binding:
        raise MobilePolicyTokenError("DENY_POLICY_TOKEN_BINDING")

    return claims
