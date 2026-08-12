"""Dedicated verification boundary for EAY AI Core -> Platform Core assertions.

This trust root is intentionally separate from the Identity Gateway internal
assertion keys. The Jarvis machine assertion carries no tenant, user, role,
permission or tool scope authority; it proves only that the caller is the EAY
AI Core service presenting a short-lived assertion for Jarvis tool execution.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import jwt
from pydantic import BaseModel, ConfigDict

JARVIS_SERVICE_ASSERTION_TYP = "opex-jarvis-service+jwt"
JARVIS_SERVICE_SUBJECT = "eay-ai-core"
JARVIS_SERVICE_PURPOSE = "jarvis-tool-execution"
JARVIS_SERVICE_ALGORITHM = "ES256"
JARVIS_SERVICE_DEFAULT_AUDIENCE = "opex-core-jarvis"
JARVIS_SERVICE_MAX_LIFETIME_SECONDS = 30
JARVIS_SERVICE_CLOCK_SKEW_SECONDS = 5
JARVIS_SERVICE_REPLAY_SKEW_SECONDS = 10

KID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
JTI_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
MAX_JWKS_BYTES = 256 * 1024
MAX_JWKS_KEYS = 16
RESERVED_PLATFORM_AUDIENCES = {
    "opex-core-api",
    "opex-core-preauth",
}
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
ALLOWED_CLAIMS = {
    "iss",
    "aud",
    "sub",
    "purpose",
    "jti",
    "iat",
    "nbf",
    "exp",
}


class JarvisServiceAssertionError(PermissionError):
    """Base denial for the Jarvis machine-identity boundary."""


class JarvisServiceAssertionInvalid(JarvisServiceAssertionError):
    """The assertion violates the Jarvis service-identity contract."""


class JarvisServiceAssertionUnavailable(JarvisServiceAssertionError):
    """Trusted Jarvis verification material is unavailable or unsafe."""


@dataclass(frozen=True)
class JarvisServiceVerifierSettings:
    jwks_file: str
    issuer: str = JARVIS_SERVICE_SUBJECT
    audience: str = JARVIS_SERVICE_DEFAULT_AUDIENCE
    max_lifetime_seconds: int = JARVIS_SERVICE_MAX_LIFETIME_SECONDS

    def __post_init__(self) -> None:
        jwks_file = self.jwks_file.strip()
        issuer = self.issuer.strip()
        audience = self.audience.strip()

        if not jwks_file:
            raise JarvisServiceAssertionUnavailable(
                "Jarvis service JWKS file is required"
            )

        if issuer != JARVIS_SERVICE_SUBJECT:
            raise JarvisServiceAssertionInvalid(
                "Jarvis service issuer must be eay-ai-core"
            )

        if (
            not audience
            or audience in RESERVED_PLATFORM_AUDIENCES
            or len(audience) > 200
        ):
            raise JarvisServiceAssertionInvalid(
                "Jarvis service audience is invalid"
            )

        if (
            isinstance(self.max_lifetime_seconds, bool)
            or not isinstance(self.max_lifetime_seconds, int)
            or not 1
            <= self.max_lifetime_seconds
            <= JARVIS_SERVICE_MAX_LIFETIME_SECONDS
        ):
            raise JarvisServiceAssertionInvalid(
                "Jarvis service assertion lifetime policy is invalid"
            )

        object.__setattr__(self, "jwks_file", jwks_file)
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "audience", audience)

    @classmethod
    def from_environment(cls) -> JarvisServiceVerifierSettings:
        raw_lifetime = os.getenv(
            "OPEX_JARVIS_SERVICE_MAX_LIFETIME_SECONDS",
            str(JARVIS_SERVICE_MAX_LIFETIME_SECONDS),
        )
        try:
            max_lifetime_seconds = int(raw_lifetime)
        except ValueError as exc:
            raise JarvisServiceAssertionInvalid(
                "Jarvis service assertion lifetime policy is invalid"
            ) from exc

        return cls(
            jwks_file=os.getenv("OPEX_JARVIS_SERVICE_JWKS_FILE", ""),
            issuer=os.getenv(
                "OPEX_JARVIS_SERVICE_ISSUER",
                JARVIS_SERVICE_SUBJECT,
            ),
            audience=os.getenv(
                "OPEX_JARVIS_SERVICE_AUDIENCE",
                JARVIS_SERVICE_DEFAULT_AUDIENCE,
            ),
            max_lifetime_seconds=max_lifetime_seconds,
        )


class VerifiedJarvisService(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_subject: str
    assertion_id: str
    issued_at: int
    expires_at: int
    replay_ttl_seconds: int


def _load_trusted_jwks(
    path_value: str,
) -> tuple[dict[str, object], ...]:
    path = Path(path_value)

    try:
        stat = path.stat()
    except OSError as exc:
        raise JarvisServiceAssertionUnavailable(
            "Trusted Jarvis verification keys are unavailable"
        ) from exc

    if (
        not path.is_file()
        or stat.st_size <= 0
        or stat.st_size > MAX_JWKS_BYTES
    ):
        raise JarvisServiceAssertionUnavailable(
            "Trusted Jarvis verification key file is invalid"
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JarvisServiceAssertionUnavailable(
            "Trusted Jarvis verification keys cannot be loaded"
        ) from exc

    if not isinstance(payload, dict) or set(payload) != {"keys"}:
        raise JarvisServiceAssertionUnavailable(
            "Trusted Jarvis JWKS document is invalid"
        )

    keys = payload.get("keys")
    if (
        not isinstance(keys, list)
        or not keys
        or len(keys) > MAX_JWKS_KEYS
    ):
        raise JarvisServiceAssertionUnavailable(
            "Trusted Jarvis JWKS key set is invalid"
        )

    normalized: list[dict[str, object]] = []
    seen_kids: set[str] = set()

    for item in keys:
        if not isinstance(item, dict):
            raise JarvisServiceAssertionUnavailable(
                "Trusted Jarvis JWK entry is invalid"
            )

        kid = item.get("kid")
        if (
            not isinstance(kid, str)
            or not KID_PATTERN.fullmatch(kid)
            or kid in seen_kids
        ):
            raise JarvisServiceAssertionUnavailable(
                "Trusted Jarvis JWK kid is invalid"
            )

        if PRIVATE_JWK_FIELDS.intersection(item):
            raise JarvisServiceAssertionUnavailable(
                "Private key material must not exist in the Jarvis JWKS"
            )

        if item.get("kty") != "EC" or item.get("crv") != "P-256":
            raise JarvisServiceAssertionUnavailable(
                "Jarvis assertion keys must use EC P-256"
            )

        if item.get("use") not in {None, "sig"}:
            raise JarvisServiceAssertionUnavailable(
                "Jarvis assertion JWK use is invalid"
            )

        if item.get("alg") not in {None, JARVIS_SERVICE_ALGORITHM}:
            raise JarvisServiceAssertionUnavailable(
                "Jarvis assertion JWK algorithm is invalid"
            )

        seen_kids.add(kid)
        normalized.append(item)

    return tuple(normalized)


def _select_verification_key(
    *,
    settings: JarvisServiceVerifierSettings,
    kid: str,
):
    matches = [
        item
        for item in _load_trusted_jwks(settings.jwks_file)
        if item.get("kid") == kid
    ]

    if len(matches) != 1:
        raise JarvisServiceAssertionInvalid(
            "Jarvis assertion signing key is not trusted"
        )

    try:
        return jwt.PyJWK.from_dict(matches[0]).key
    except Exception as exc:
        raise JarvisServiceAssertionUnavailable(
            "Trusted Jarvis verification key is unusable"
        ) from exc


def verify_jarvis_service_assertion(
    token: str,
    settings: JarvisServiceVerifierSettings,
    *,
    now: float | None = None,
) -> VerifiedJarvisService:
    if (
        not isinstance(token, str)
        or not token
        or len(token) > 8192
    ):
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion is invalid"
        )

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion header is invalid"
        ) from exc

    if set(header) != {"alg", "kid", "typ"}:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion header contract is invalid"
        )

    if header.get("alg") != JARVIS_SERVICE_ALGORITHM:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion algorithm is not allowed"
        )

    kid = header.get("kid")
    if not isinstance(kid, str) or not KID_PATTERN.fullmatch(kid):
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion kid is invalid"
        )

    if header.get("typ") != JARVIS_SERVICE_ASSERTION_TYP:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion type is invalid"
        )

    verification_key = _select_verification_key(
        settings=settings,
        kid=kid,
    )

    try:
        claims = jwt.decode(
            token,
            verification_key,
            algorithms=[JARVIS_SERVICE_ALGORITHM],
            audience=settings.audience,
            issuer=settings.issuer,
            leeway=JARVIS_SERVICE_CLOCK_SKEW_SECONDS,
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
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion signature or claims are invalid"
        ) from exc

    if set(claims) != ALLOWED_CLAIMS:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion claim contract is invalid"
        )

    if claims.get("sub") != JARVIS_SERVICE_SUBJECT:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion subject is invalid"
        )

    if claims.get("purpose") != JARVIS_SERVICE_PURPOSE:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion purpose is invalid"
        )

    assertion_id = claims.get("jti")
    if (
        not isinstance(assertion_id, str)
        or not JTI_PATTERN.fullmatch(assertion_id)
    ):
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion identifier is invalid"
        )

    timestamps: dict[str, int] = {}
    for claim_name in ("iat", "nbf", "exp"):
        value = claims.get(claim_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise JarvisServiceAssertionInvalid(
                "Jarvis service assertion timestamps are invalid"
            )
        timestamps[claim_name] = value

    issued_at = timestamps["iat"]
    not_before = timestamps["nbf"]
    expires_at = timestamps["exp"]

    if not_before != issued_at:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion nbf must equal iat"
        )

    lifetime = expires_at - issued_at
    if lifetime <= 0 or lifetime > settings.max_lifetime_seconds:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion lifetime is invalid"
        )

    current_time = time.time() if now is None else now
    if issued_at > current_time + JARVIS_SERVICE_CLOCK_SKEW_SECONDS:
        raise JarvisServiceAssertionInvalid(
            "Jarvis service assertion issue time is invalid"
        )

    replay_ttl_seconds = min(
        JARVIS_SERVICE_MAX_LIFETIME_SECONDS
        + JARVIS_SERVICE_REPLAY_SKEW_SECONDS,
        max(1, int(expires_at - current_time) + JARVIS_SERVICE_REPLAY_SKEW_SECONDS),
    )

    return VerifiedJarvisService(
        service_subject=JARVIS_SERVICE_SUBJECT,
        assertion_id=assertion_id,
        issued_at=issued_at,
        expires_at=expires_at,
        replay_ttl_seconds=replay_ttl_seconds,
    )
