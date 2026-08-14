"""Verification boundary for OPEX-internal identity assertions."""

import json
import re
import time
from pathlib import Path
from uuid import UUID

import jwt
from pydantic import BaseModel

from app.core.config import Settings

INTERNAL_ASSERTION_TYP = "opex-internal+jwt"
INTERNAL_SERVICE_ASSERTION_TYP = "opex-internal-service+jwt"

ALLOWED_CLAIMS = {
    "iss",
    "aud",
    "sub",
    "tenant_id",
    "jti",
    "iat",
    "nbf",
    "exp",
}

SERVICE_ALLOWED_CLAIMS = {
    "iss",
    "aud",
    "sub",
    "purpose",
    "jti",
    "iat",
    "nbf",
    "exp",
}

KID_PATTERN = re.compile(
    r"^[A-Za-z0-9._:-]{1,128}$"
)

JTI_PATTERN = re.compile(
    r"^[A-Za-z0-9._:-]{16,128}$"
)

MAX_JWKS_BYTES = 256 * 1024
MAX_JWKS_KEYS = 16

PRIVATE_JWK_FIELDS = {
    "d",
    "p",
    "q",
    "dp",
    "dq",
    "qi",
    "oth",
    "k",
}


class InternalAssertionError(Exception):
    """Base class for internal assertion failures."""


class InternalAssertionInvalid(InternalAssertionError):
    """Assertion is invalid or violates the internal contract."""


class InternalAssertionUnavailable(InternalAssertionError):
    """Trusted verification material is unavailable or invalid."""


class VerifiedInternalIdentity(BaseModel):
    tenant_id: UUID
    membership_id: UUID
    assertion_id: str


class VerifiedInternalService(BaseModel):
    service_subject: str
    assertion_id: str


def _load_trusted_jwks(
    path_value: str,
) -> tuple[dict[str, object], ...]:
    path = Path(path_value)

    try:
        stat = path.stat()
    except OSError as exc:
        raise InternalAssertionUnavailable(
            "Trusted internal verification keys are unavailable"
        ) from exc

    if (
        not path.is_file()
        or stat.st_size <= 0
        or stat.st_size > MAX_JWKS_BYTES
    ):
        raise InternalAssertionUnavailable(
            "Trusted internal verification key file is invalid"
        )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InternalAssertionUnavailable(
            "Trusted internal verification keys cannot be loaded"
        ) from exc

    if not isinstance(payload, dict):
        raise InternalAssertionUnavailable(
            "Trusted internal JWKS document is invalid"
        )

    keys = payload.get("keys")

    if (
        not isinstance(keys, list)
        or not keys
        or len(keys) > MAX_JWKS_KEYS
    ):
        raise InternalAssertionUnavailable(
            "Trusted internal JWKS key set is invalid"
        )

    normalized: list[dict[str, object]] = []
    seen_kids: set[str] = set()

    for item in keys:
        if not isinstance(item, dict):
            raise InternalAssertionUnavailable(
                "Trusted internal JWK entry is invalid"
            )

        kid = item.get("kid")

        if (
            not isinstance(kid, str)
            or not KID_PATTERN.fullmatch(kid)
            or kid in seen_kids
        ):
            raise InternalAssertionUnavailable(
                "Trusted internal JWK kid is invalid"
            )

        if PRIVATE_JWK_FIELDS.intersection(
            item
        ):
            raise InternalAssertionUnavailable(
                "Private key material must not exist "
                "in the Core API JWKS"
            )

        if item.get("kty") != "EC":
            raise InternalAssertionUnavailable(
                "Internal assertion keys must use EC"
            )

        if item.get("crv") != "P-256":
            raise InternalAssertionUnavailable(
                "Internal assertion keys must use P-256"
            )

        if item.get("use") not in {
            None,
            "sig",
        }:
            raise InternalAssertionUnavailable(
                "Internal assertion JWK use is invalid"
            )

        if item.get("alg") not in {
            None,
            "ES256",
        }:
            raise InternalAssertionUnavailable(
                "Internal assertion JWK algorithm is invalid"
            )

        seen_kids.add(kid)
        normalized.append(item)

    return tuple(normalized)


def _select_verification_key(
    *,
    settings: Settings,
    kid: str,
    algorithm: str,
):
    keys = _load_trusted_jwks(
        settings.internal_assertion_jwks_file
    )

    matches = [
        item
        for item in keys
        if item.get("kid") == kid
    ]

    if len(matches) != 1:
        raise InternalAssertionInvalid(
            "Internal assertion signing key is not trusted"
        )

    candidate = matches[0]

    configured_alg = candidate.get("alg")

    if (
        configured_alg is not None
        and configured_alg != algorithm
    ):
        raise InternalAssertionInvalid(
            "Internal assertion key algorithm mismatch"
        )

    try:
        return jwt.PyJWK.from_dict(
            candidate
        ).key
    except Exception as exc:
        raise InternalAssertionUnavailable(
            "Trusted internal verification key is unusable"
        ) from exc



def verify_internal_service_assertion(
    token: str,
    settings: Settings,
) -> VerifiedInternalService:
    """Verify a Gateway service assertion with no tenant authority."""
    if (
        not isinstance(token, str)
        or not token
        or len(token) > 8192
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion is invalid"
        )

    try:
        header = jwt.get_unverified_header(
            token
        )
    except jwt.PyJWTError as exc:
        raise InternalAssertionInvalid(
            "Internal service assertion header is invalid"
        ) from exc

    if set(header) != {
        "alg",
        "kid",
        "typ",
    }:
        raise InternalAssertionInvalid(
            "Internal service assertion header contract is invalid"
        )

    algorithm = header.get(
        "alg"
    )
    kid = header.get(
        "kid"
    )
    token_type = header.get(
        "typ"
    )

    if (
        not isinstance(
            algorithm,
            str,
        )
        or algorithm
        not in settings.
        internal_assertion_algorithm_list
        or algorithm != "ES256"
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion algorithm is not allowed"
        )

    if (
        not isinstance(
            kid,
            str,
        )
        or not KID_PATTERN.fullmatch(
            kid
        )
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion kid is invalid"
        )

    if (
        token_type
        != INTERNAL_SERVICE_ASSERTION_TYP
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion type is invalid"
        )

    verification_key = (
        _select_verification_key(
            settings=settings,
            kid=kid,
            algorithm=algorithm,
        )
    )

    try:
        claims = jwt.decode(
            token,
            verification_key,
            algorithms=[
                "ES256",
            ],
            audience=(
                settings.
                internal_service_assertion_audience
            ),
            issuer=(
                settings.
                internal_assertion_issuer
            ),
            leeway=5,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "jti",
                    "iat",
                    "nbf",
                    "exp",
                ],
            },
        )
    except jwt.PyJWTError as exc:
        raise InternalAssertionInvalid(
            "Internal service assertion signature or claims are invalid"
        ) from exc

    if (
        set(claims)
        != SERVICE_ALLOWED_CLAIMS
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion claim contract is invalid"
        )

    if (
        claims.get(
            "purpose"
        )
        != "preauth"
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion purpose is invalid"
        )

    if (
        claims.get(
            "sub"
        )
        != "identity-gateway"
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion subject is invalid"
        )

    assertion_id = claims[
        "jti"
    ]

    if (
        not isinstance(
            assertion_id,
            str,
        )
        or not JTI_PATTERN.fullmatch(
            assertion_id
        )
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion identifier is invalid"
        )

    for claim_name in (
        "iat",
        "nbf",
        "exp",
    ):
        value = claims[
            claim_name
        ]

        if (
            isinstance(
                value,
                bool,
            )
            or not isinstance(
                value,
                (
                    int,
                    float,
                ),
            )
        ):
            raise InternalAssertionInvalid(
                "Internal service assertion timestamps are invalid"
            )

    issued_at = float(
        claims["iat"]
    )

    not_before = float(
        claims["nbf"]
    )

    expires_at = float(
        claims["exp"]
    )

    if (
        not_before
        != issued_at
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion nbf must equal iat"
        )

    lifetime = (
        expires_at
        - issued_at
    )

    if (
        lifetime <= 0
        or lifetime
        > settings.
        internal_assertion_max_lifetime_seconds
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion lifetime is invalid"
        )

    if (
        issued_at
        > time.time() + 5
    ):
        raise InternalAssertionInvalid(
            "Internal service assertion issue time is invalid"
        )

    return VerifiedInternalService(
        service_subject=(
            "identity-gateway"
        ),
        assertion_id=(
            assertion_id
        ),
    )


def verify_internal_identity_assertion(
    token: str,
    settings: Settings,
) -> VerifiedInternalIdentity:
    if (
        not isinstance(token, str)
        or not token
        or len(token) > 8192
    ):
        raise InternalAssertionInvalid(
            "Internal assertion is invalid"
        )

    try:
        header = jwt.get_unverified_header(
            token
        )
    except jwt.PyJWTError as exc:
        raise InternalAssertionInvalid(
            "Internal assertion header is invalid"
        ) from exc

    # No jku, x5u, jwk, x5c, crit or extension fields.
    # The entire trusted header contract is explicit.
    if set(header) != {
        "alg",
        "kid",
        "typ",
    }:
        raise InternalAssertionInvalid(
            "Internal assertion header contract is invalid"
        )

    algorithm = header.get("alg")
    kid = header.get("kid")
    token_type = header.get("typ")

    if (
        not isinstance(algorithm, str)
        or algorithm
        not in settings.internal_assertion_algorithm_list
    ):
        raise InternalAssertionInvalid(
            "Internal assertion algorithm is not allowed"
        )

    if algorithm != "ES256":
        raise InternalAssertionInvalid(
            "Internal assertion algorithm is not allowed"
        )

    if (
        not isinstance(kid, str)
        or not KID_PATTERN.fullmatch(kid)
    ):
        raise InternalAssertionInvalid(
            "Internal assertion kid is invalid"
        )

    if token_type != INTERNAL_ASSERTION_TYP:
        raise InternalAssertionInvalid(
            "Internal assertion type is invalid"
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
            algorithms=[
                "ES256",
            ],
            audience=(
                settings.internal_assertion_audience
            ),
            issuer=(
                settings.internal_assertion_issuer
            ),
            leeway=5,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "tenant_id",
                    "jti",
                    "iat",
                    "nbf",
                    "exp",
                ],
            },
        )
    except jwt.PyJWTError as exc:
        raise InternalAssertionInvalid(
            "Internal assertion signature or claims are invalid"
        ) from exc

    # This deliberately rejects role, permission, scope, provider,
    # email or any future unexpected claim smuggling.
    if set(claims) != ALLOWED_CLAIMS:
        raise InternalAssertionInvalid(
            "Internal assertion claim contract is invalid"
        )

    try:
        membership_id = UUID(
            str(claims["sub"])
        )

        tenant_id = UUID(
            str(claims["tenant_id"])
        )
    except (TypeError, ValueError) as exc:
        raise InternalAssertionInvalid(
            "Internal assertion identity is invalid"
        ) from exc

    assertion_id = claims["jti"]

    if (
        not isinstance(assertion_id, str)
        or not JTI_PATTERN.fullmatch(
            assertion_id
        )
    ):
        raise InternalAssertionInvalid(
            "Internal assertion identifier is invalid"
        )

    for claim_name in (
        "iat",
        "nbf",
        "exp",
    ):
        value = claims[claim_name]

        if (
            isinstance(value, bool)
            or not isinstance(
                value,
                (
                    int,
                    float,
                ),
            )
        ):
            raise InternalAssertionInvalid(
                "Internal assertion timestamps are invalid"
            )

    issued_at = float(
        claims["iat"]
    )

    not_before = float(
        claims["nbf"]
    )

    expires_at = float(
        claims["exp"]
    )

    if not_before != issued_at:
        raise InternalAssertionInvalid(
            "Internal assertion nbf must equal iat"
        )

    lifetime = (
        expires_at
        - issued_at
    )

    if (
        lifetime <= 0
        or lifetime
        > settings.internal_assertion_max_lifetime_seconds
    ):
        raise InternalAssertionInvalid(
            "Internal assertion lifetime is invalid"
        )

    if issued_at > time.time() + 5:
        raise InternalAssertionInvalid(
            "Internal assertion issue time is invalid"
        )

    return VerifiedInternalIdentity(
        tenant_id=tenant_id,
        membership_id=membership_id,
        assertion_id=assertion_id,
    )
