"""Cryptographic identity boundary for EAY Jarvis service calls.

This contract is intentionally distinct from the Phase 1 Identity Gateway
`preauth` service assertion. A token valid for one purpose must never be
accepted for the other.
"""

from __future__ import annotations

import time

import jwt
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.core.internal_identity import (
    JTI_PATTERN,
    KID_PATTERN,
    InternalAssertionInvalid,
    _select_verification_key,
)

JARVIS_SERVICE_ASSERTION_TYP = "opex-jarvis-service+jwt"
JARVIS_SERVICE_AUDIENCE = "opex-core-jarvis"
JARVIS_SERVICE_SUBJECT = "eay-ai-core"
JARVIS_SERVICE_PURPOSE = "jarvis-tool-execution"

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


class VerifiedJarvisService(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_subject: str
    assertion_id: str


def verify_jarvis_service_assertion(
    token: str,
    settings: Settings,
) -> VerifiedJarvisService:
    """Verify an EAY AI Core -> Core API service assertion."""

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

    if (
        not isinstance(algorithm, str)
        or algorithm
        not in settings.internal_assertion_algorithm_list
        or algorithm != "ES256"
    ):
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

    verification_key = _select_verification_key(
        settings=settings,
        kid=kid,
        algorithm=algorithm,
    )

    try:
        claims = jwt.decode(
            token,
            verification_key,
            algorithms=["ES256"],
            audience=JARVIS_SERVICE_AUDIENCE,
            issuer=settings.internal_assertion_issuer,
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

    if claims.get("aud") != JARVIS_SERVICE_AUDIENCE:
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
        > settings.internal_assertion_max_lifetime_seconds
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
