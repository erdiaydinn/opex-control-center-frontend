"""Private-key service identity for EAY AI Core -> Platform Core calls.

The signer is intentionally narrow: it can issue only the Jarvis tool
execution assertion understood by the Platform Core verifier. User identity,
tenant identity and permission scopes never appear in this machine token.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

JARVIS_SERVICE_ASSERTION_TYP = "opex-jarvis-service+jwt"
JARVIS_SERVICE_SUBJECT = "eay-ai-core"
JARVIS_SERVICE_PURPOSE = "jarvis-tool-execution"
JARVIS_SERVICE_ALGORITHM = "ES256"
JARVIS_SERVICE_DEFAULT_AUDIENCE = "opex-core-jarvis"
JARVIS_SERVICE_DEFAULT_LIFETIME_SECONDS = 30
JARVIS_SERVICE_MAX_LIFETIME_SECONDS = 30

KID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
RESERVED_PLATFORM_AUDIENCES = {
    "opex-core-api",
    "opex-core-preauth",
}


class JarvisServiceIdentityError(RuntimeError):
    """Fail-closed Jarvis machine identity configuration error."""


@dataclass(frozen=True)
class JarvisServiceIdentitySettings:
    private_key_file: str
    signing_kid: str
    issuer: str = JARVIS_SERVICE_SUBJECT
    audience: str = JARVIS_SERVICE_DEFAULT_AUDIENCE
    lifetime_seconds: int = JARVIS_SERVICE_DEFAULT_LIFETIME_SECONDS

    def __post_init__(self) -> None:
        private_key_file = self.private_key_file.strip()
        signing_kid = self.signing_kid.strip()
        issuer = self.issuer.strip()
        audience = self.audience.strip()

        if not private_key_file:
            raise JarvisServiceIdentityError(
                "Jarvis service private key file is required"
            )

        if not KID_PATTERN.fullmatch(signing_kid):
            raise JarvisServiceIdentityError(
                "Jarvis service signing kid is invalid"
            )

        if issuer != JARVIS_SERVICE_SUBJECT:
            raise JarvisServiceIdentityError(
                "Jarvis service issuer must be eay-ai-core"
            )

        if (
            not audience
            or audience in RESERVED_PLATFORM_AUDIENCES
            or len(audience) > 200
        ):
            raise JarvisServiceIdentityError(
                "Jarvis service audience is invalid"
            )

        if (
            isinstance(self.lifetime_seconds, bool)
            or not isinstance(self.lifetime_seconds, int)
            or not 1 <= self.lifetime_seconds <= JARVIS_SERVICE_MAX_LIFETIME_SECONDS
        ):
            raise JarvisServiceIdentityError(
                "Jarvis service assertion lifetime is invalid"
            )

        object.__setattr__(self, "private_key_file", private_key_file)
        object.__setattr__(self, "signing_kid", signing_kid)
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "audience", audience)

    @classmethod
    def from_environment(cls) -> JarvisServiceIdentitySettings:
        return cls(
            private_key_file=os.getenv(
                "EAY_JARVIS_SERVICE_PRIVATE_KEY_FILE",
                "",
            ),
            signing_kid=os.getenv(
                "EAY_JARVIS_SERVICE_SIGNING_KID",
                "",
            ),
            issuer=os.getenv(
                "EAY_JARVIS_SERVICE_ISSUER",
                JARVIS_SERVICE_SUBJECT,
            ),
            audience=os.getenv(
                "EAY_JARVIS_SERVICE_AUDIENCE",
                JARVIS_SERVICE_DEFAULT_AUDIENCE,
            ),
            lifetime_seconds=int(
                os.getenv(
                    "EAY_JARVIS_SERVICE_LIFETIME_SECONDS",
                    str(JARVIS_SERVICE_DEFAULT_LIFETIME_SECONDS),
                )
            ),
        )


class JarvisServiceIdentitySigner:
    """Sign one-purpose, short-lived AI Core machine assertions."""

    def __init__(
        self,
        settings: JarvisServiceIdentitySettings,
    ) -> None:
        self._settings = settings
        self._private_key = self._load_private_key(
            settings.private_key_file
        )

    @staticmethod
    def _load_private_key(
        private_key_file: str,
    ) -> ec.EllipticCurvePrivateKey:
        path = Path(private_key_file)

        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise JarvisServiceIdentityError(
                "Jarvis service private key cannot be read"
            ) from exc

        try:
            key = serialization.load_pem_private_key(
                raw,
                password=None,
            )
        except (TypeError, ValueError) as exc:
            raise JarvisServiceIdentityError(
                "Jarvis service private key is invalid"
            ) from exc

        if (
            not isinstance(key, ec.EllipticCurvePrivateKey)
            or not isinstance(key.curve, ec.SECP256R1)
        ):
            raise JarvisServiceIdentityError(
                "Jarvis service private key must be EC P-256"
            )

        return key

    def public_jwks(self) -> dict[str, object]:
        public_jwk = json.loads(
            ECAlgorithm.to_jwk(
                self._private_key.public_key()
            )
        )
        public_jwk.update(
            {
                "kid": self._settings.signing_kid,
                "use": "sig",
                "alg": JARVIS_SERVICE_ALGORITHM,
            }
        )

        if "d" in public_jwk:
            raise JarvisServiceIdentityError(
                "Private key material leaked into Jarvis JWKS"
            )

        return {"keys": [public_jwk]}

    def issue_tool_execution_assertion(self) -> str:
        now = int(time.time())
        expires_at = now + self._settings.lifetime_seconds

        claims = {
            "iss": self._settings.issuer,
            "aud": self._settings.audience,
            "sub": JARVIS_SERVICE_SUBJECT,
            "purpose": JARVIS_SERVICE_PURPOSE,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": expires_at,
        }

        return jwt.encode(
            claims,
            self._private_key,
            algorithm=JARVIS_SERVICE_ALGORITHM,
            headers={
                "kid": self._settings.signing_kid,
                "typ": JARVIS_SERVICE_ASSERTION_TYP,
            },
        )
