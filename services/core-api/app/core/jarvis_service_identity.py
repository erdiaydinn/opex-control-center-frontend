"""Cryptographic identity boundary for EAY Jarvis service calls.

Jarvis uses an independent service key/JWKS trust root. The Phase 1 Identity
Gateway `preauth` signing key is deliberately not trusted by this verifier.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

import jwt
from jwt.algorithms import ECAlgorithm
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.internal_identity import (
    JTI_PATTERN,
    KID_PATTERN,
    InternalAssertionInvalid,
    InternalAssertionUnavailable,
)

JARVIS_SERVICE_ASSERTION_TYP = "opex-jarvis-service+jwt"
JARVIS_SERVICE_SUBJECT = "eay-ai-core"
JARVIS_SERVICE_PURPOSE = "jarvis-tool-execution"
JARVIS_SERVICE_ALGORITHM = "ES256"

JARVIS_SERVICE_ALLOWED_CLAIMS = {
    "iss",
    "aud",
    "sub",
    "purpose",
    "jti",
    "iat",
    "nbf",
    "exp",
}

RESERVED_PLATFORM_AUDIENCES = {
    "opex-core-api",
    "opex-core-preauth",
}


class JarvisServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPEX_JARVIS_SERVICE_",
        case_sensitive=False,
        extra="ignore",
    )

    enabled: bool = False
    assertion_issuer: str = JARVIS_SERVICE_SUBJECT
    assertion_audience: str = "opex-core-jarvis"
    assertion_jwks_file: str = ""
    assertion_max_lifetime_seconds: int = Field(
        default=30,
        ge=15,
        le=60,
    )

    @model_validator(mode="after")
    def validate_identity_boundary(self) -> JarvisServiceSettings:
        issuer = self.assertion_issuer.strip()
        audience = self.assertion_audience.strip()
        jwks_file = self.assertion_jwks_file.strip()

        if not issuer or len(issuer) > 200:
            raise ValueError(
                "Jarvis service assertion issuer is invalid"
            )

        if issuer == "opex-identity-gateway":
            raise ValueError(
                "Jarvis service must not reuse Identity Gateway issuer"
            )

        if (
            not audience
            or len(audience) > 200
            or audience in RESERVED_PLATFORM_AUDIENCES
        ):
            raise ValueError(
                "Jarvis service assertion audience is invalid"
            )

        if self.enabled and not jwks_file:
            raise ValueError(
                "Jarvis service JWKS file is required when enabled"
            )

        object.__setattr__(
            self,
            "assertion_issuer",
            issuer,
        )
        object.__setattr__(
            self,
            "assertion_audience",
            audience,
        )
        object.__setattr__(
            self,
            "assertion_jwks_file",
            jwks_file,
        )
        return self


@lru_cache
def get_jarvis_service_settings() -> JarvisServiceSettings:
    return JarvisServiceSettings()


class VerifiedJarvisService(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_subject: str
    assertion_id: str


@lru_cache(maxsize=4)
def _load_jarvis_jwks(
    jwks_file: str,
) -> dict[str, object]:
    if not jwks_file:
        raise InternalAssertionUnavailable(
            "Jarvis service JWKS file is not configured"
        )

    path = Path(jwks_file)

    try:
        raw = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InternalAssertionUnavailable(
            "Jarvis service JWKS cannot be loaded"
        ) from exc

    if not isinstance(raw, dict):
        raise InternalAssertionUnavailable(
            "Jarvis service JWKS root is invalid"
        )

    keys = raw.get("keys")

    if not isinstance(keys, list) or not keys:
        raise InternalAssertionUnavailable(
            "Jarvis service JWKS has no verification keys"
        )

    if len(keys) > 16:
        raise InternalAssertionUnavailable(
            "Jarvis service JWKS has too many keys"
        )

    return raw


def _select_jarvis_verification_key(
    *,
    settings: JarvisServiceSettings,
    kid: str,
    algorithm: str,
):
    jwks = _load_jarvis_jwks(
        settings.assertion_jwks_file
    )
    matches: list[dict[str, object]] = []

    for item in jwks["keys"]:
        if not isinstance(item, dict):
            continue

        if item.get("kid") != kid:
            continue

        if (
            item.get("kty") != "EC"
            or item.get("crv") != "P-256"
            or item.get("alg") != algorithm
            or item.get("use") != "sig"
        ):
            raise InternalAssertionInvalid(
                "Jarvis service verification key contract is invalid"
            )

        if "d" in item:
            raise InternalAssertionInvalid(
                "Jarvis service JWKS contains private key material"
            )

        matches.append(item)

    if len(matches) != 1:
        raise InternalAssertionInvalid(
            "Jarvis service verification key is ambiguous or missing"
        )

    try:
        return ECAlgorithm.from_jwk(matches[0])
    except (TypeError, ValueError, jwt.PyJWTError) as exc:
        raise InternalAssertionInvalid(
            "Jarvis service verification key is invalid"
        ) from exc


def verify_jarvis_service_assertion(
    token: str,
    settings: JarvisServiceSettings,
) -> VerifiedJarvisService:
    """Verify an independently signed EAY AI Core service assertion."""

    if not settings.enabled:
        raise InternalAssertionUnavailable(
            "Jarvis service identity is disabled"
        )

    if (
        not isinstance(token, str)
        or not token
        or len(token) > 8192
    ):
        raise InternalAssertionInvalid(
            "Jarvis service assertion is invalid"
        )

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise InternalAssertionInvalid(
            "Jarvis service assertion header is invalid"
        ) from exc

    if set(header) != {
        "alg",
        "kid",
        "typ",
    }:
        raise InternalAssertionInvalid(
            "Jarvis service assertion header contract is invalid"
        )

    algorithm = header.get("alg")
    kid = header.get("kid")
    token_type = header.get("typ")

    if algorithm != JARVIS_SERVICE_ALGORITHM:
        raise InternalAssertionInvalid(
            "Jarvis service assertion algorithm is not allowed"
        )

    if (
        not isinstance(kid, str)
        or not KID_PATTERN.fullmatch(kid)
    ):
        raise InternalAssertionInvalid(
            "Jarvis service assertion kid is invalid"
        )

    if token_type != JARVIS_SERVICE_ASSERTION_TYP:
        raise InternalAssertionInvalid(
            "Jarvis service assertion type is invalid"
        )

    verification_key = _select_jarvis_verification_key(
        settings=settings,
        kid=kid,
        algorithm=JARVIS_SERVICE_ALGORITHM,
    )

    try:
        claims = jwt.decode(
            token,
            verification_key,
            algorithms=[JARVIS_SERVICE_ALGORITHM],
            audience=settings.assertion_audience,
            issuer=settings.assertion_issuer,
            leeway=5,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "purpose",
                    "jti",
                    "iat",
                    "nbf",
                    "exp",
                ],
            },
        )
    except jwt.PyJWTError as exc:
        raise InternalAssertionInvalid(
            "Jarvis service assertion signature or claims are invalid"
        ) from exc

    if set(claims) != JARVIS_SERVICE_ALLOWED_CLAIMS:
        raise InternalAssertionInvalid(
            "Jarvis service assertion claim contract is invalid"
        )

    if claims.get("aud") != settings.assertion_audience:
        raise InternalAssertionInvalid(
            "Jarvis service assertion audience is invalid"
        )

    if claims.get("sub") != JARVIS_SERVICE_SUBJECT:
        raise InternalAssertionInvalid(
            "Jarvis service assertion subject is invalid"
        )

    if claims.get("purpose") != JARVIS_SERVICE_PURPOSE:
        raise InternalAssertionInvalid(
            "Jarvis service assertion purpose is invalid"
        )

    assertion_id = claims["jti"]

    if (
        not isinstance(assertion_id, str)
        or not JTI_PATTERN.fullmatch(assertion_id)
    ):
        raise InternalAssertionInvalid(
            "Jarvis service assertion identifier is invalid"
        )

    for claim_name in (
        "iat",
        "nbf",
        "exp",
    ):
        value = claims[claim_name]

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise InternalAssertionInvalid(
                "Jarvis service assertion timestamps are invalid"
            )

    issued_at = float(claims["iat"])
    not_before = float(claims["nbf"])
    expires_at = float(claims["exp"])

    if not_before != issued_at:
        raise InternalAssertionInvalid(
            "Jarvis service assertion nbf must equal iat"
        )

    lifetime = expires_at - issued_at

    if (
        lifetime <= 0
        or lifetime
        > settings.assertion_max_lifetime_seconds
    ):
        raise InternalAssertionInvalid(
            "Jarvis service assertion lifetime is invalid"
        )

    if issued_at > time.time() + 5:
        raise InternalAssertionInvalid(
            "Jarvis service assertion issue time is invalid"
        )

    return VerifiedJarvisService(
        service_subject=JARVIS_SERVICE_SUBJECT,
        assertion_id=assertion_id,
    )
