"""Private signing boundary for the OPEX Identity Gateway."""

from dataclasses import dataclass
import json
import os
import time
from pathlib import Path
import re
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm


INTERNAL_ASSERTION_TYP = "opex-internal+jwt"
INTERNAL_SERVICE_ASSERTION_TYP = "opex-internal-service+jwt"
AI_TENANT_CONTEXT_ASSERTION_TYP = "eay-ai-tenant-context+jwt"
AI_TENANT_CONTEXT_PURPOSE = "grounded-retrieval"

KID_PATTERN = re.compile(
    r"^[A-Za-z0-9._:-]{1,128}$"
)

MAX_PRIVATE_KEY_BYTES = 64 * 1024


class IdentityGatewayConfigurationError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class GatewaySettings:
    environment: str
    issuer: str
    audience: str
    signing_key_file: str
    signing_kid: str
    assertion_lifetime_seconds: int
    service_audience: str = "opex-core-preauth"
    ai_tenant_context_audience: str = "eay-ai-core-grounded-retrieval"

    @classmethod
    def from_environment(
        cls,
    ) -> "GatewaySettings":
        environment = os.getenv(
            "OPEX_ENVIRONMENT",
            "development",
        ).strip()

        issuer = os.getenv(
            "OPEX_INTERNAL_ASSERTION_ISSUER",
            "opex-identity-gateway",
        ).strip()

        audience = os.getenv(
            "OPEX_INTERNAL_ASSERTION_AUDIENCE",
            "opex-core-api",
        ).strip()

        service_audience = os.getenv(
            "OPEX_INTERNAL_SERVICE_ASSERTION_AUDIENCE",
            "opex-core-preauth",
        ).strip()

        ai_tenant_context_audience = os.getenv(
            "OPEX_AI_TENANT_CONTEXT_AUDIENCE",
            "eay-ai-core-grounded-retrieval",
        ).strip()

        signing_key_file = os.getenv(
            "OPEX_IDENTITY_GATEWAY_SIGNING_KEY_FILE",
            "",
        ).strip()

        signing_kid = os.getenv(
            "OPEX_IDENTITY_GATEWAY_SIGNING_KID",
            "",
        ).strip()

        try:
            lifetime = int(
                os.getenv(
                    "OPEX_INTERNAL_ASSERTION_LIFETIME_SECONDS",
                    "30",
                )
            )
        except ValueError as exc:
            raise IdentityGatewayConfigurationError(
                "Assertion lifetime is invalid"
            ) from exc

        if not issuer:
            raise IdentityGatewayConfigurationError(
                "Internal assertion issuer is required"
            )

        if not audience:
            raise IdentityGatewayConfigurationError(
                "Internal assertion audience is required"
            )

        if not service_audience:
            raise IdentityGatewayConfigurationError(
                "Internal service assertion audience is required"
            )

        if service_audience == audience:
            raise IdentityGatewayConfigurationError(
                "Internal service assertion audience must differ "
                "from end-user assertion audience"
            )

        if not ai_tenant_context_audience:
            raise IdentityGatewayConfigurationError(
                "AI tenant-context audience is required"
            )

        if ai_tenant_context_audience in {
            audience,
            service_audience,
        }:
            raise IdentityGatewayConfigurationError(
                "AI tenant-context audience must be dedicated"
            )

        if not signing_key_file:
            raise IdentityGatewayConfigurationError(
                "Signing key file is required"
            )

        if not KID_PATTERN.fullmatch(
            signing_kid
        ):
            raise IdentityGatewayConfigurationError(
                "Signing key identifier is invalid"
            )

        if not 15 <= lifetime <= 60:
            raise IdentityGatewayConfigurationError(
                "Assertion lifetime must be between "
                "15 and 60 seconds"
            )

        if (
            environment
            in {
                "staging",
                "production",
            }
            and os.getenv(
                "OPEX_IDENTITY_GATEWAY_SIGNING_KEY",
                "",
            ).strip()
        ):
            raise IdentityGatewayConfigurationError(
                "Private signing material must not "
                "be supplied through environment variables"
            )

        return cls(
            environment=environment,
            issuer=issuer,
            audience=audience,
            signing_key_file=signing_key_file,
            service_audience=service_audience,
            ai_tenant_context_audience=ai_tenant_context_audience,
            signing_kid=signing_kid,
            assertion_lifetime_seconds=lifetime,
        )


class IdentitySigner:
    def __init__(
        self,
        settings: GatewaySettings,
    ) -> None:
        self.settings = settings
        self._private_key = (
            self._load_private_key()
        )

        self._jwks = (
            self._derive_public_jwks()
        )

    def _load_private_key(
        self,
    ) -> ec.EllipticCurvePrivateKey:
        path = Path(
            self.settings.signing_key_file
        )

        try:
            stat = path.stat()
        except OSError as exc:
            raise IdentityGatewayConfigurationError(
                "Signing key is unavailable"
            ) from exc

        if (
            not path.is_file()
            or stat.st_size <= 0
            or stat.st_size
            > MAX_PRIVATE_KEY_BYTES
        ):
            raise IdentityGatewayConfigurationError(
                "Signing key file is invalid"
            )

        try:
            key = (
                serialization.load_pem_private_key(
                    path.read_bytes(),
                    password=None,
                )
            )
        except Exception as exc:
            raise IdentityGatewayConfigurationError(
                "Signing key cannot be loaded"
            ) from exc

        if not isinstance(
            key,
            ec.EllipticCurvePrivateKey,
        ):
            raise IdentityGatewayConfigurationError(
                "Signing key must be an EC private key"
            )

        if not isinstance(
            key.curve,
            ec.SECP256R1,
        ):
            raise IdentityGatewayConfigurationError(
                "Signing key must use P-256"
            )

        return key

    def _derive_public_jwks(
        self,
    ) -> dict[str, object]:
        public_jwk = json.loads(
            ECAlgorithm.to_jwk(
                self._private_key.public_key()
            )
        )

        public_jwk.update(
            {
                "kid":
                    self.settings.signing_kid,
                "use":
                    "sig",
                "alg":
                    "ES256",
            }
        )

        forbidden_private_fields = {
            "d",
            "p",
            "q",
            "dp",
            "dq",
            "qi",
            "oth",
            "k",
        }

        if (
            forbidden_private_fields
            & set(public_jwk)
        ):
            raise IdentityGatewayConfigurationError(
                "Public JWKS contains private material"
            )

        return {
            "keys": [
                public_jwk,
            ],
        }

    def public_jwks(
        self,
    ) -> dict[str, object]:
        return json.loads(
            json.dumps(
                self._jwks
            )
        )

    def issue_ai_tenant_context_assertion(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_subject: str,
    ) -> str:
        """Issue a short-lived, AI-only tenant context assertion.

        Trusted server-side code must call this only after provider verification,
        external-identity resolution and membership authorization. It is not an
        end-user credential and must never be exposed through an HTTP issuance
        endpoint.
        """
        normalized_actor = actor_subject.strip()
        if not normalized_actor or len(normalized_actor) > 255:
            raise ValueError("AI tenant-context actor is invalid")

        now = int(time.time())
        payload = {
            "iss": self.settings.issuer,
            "aud": self.settings.ai_tenant_context_audience,
            "sub": normalized_actor,
            "tenant_id": str(tenant_id),
            "membership_id": str(membership_id),
            "purpose": AI_TENANT_CONTEXT_PURPOSE,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + self.settings.assertion_lifetime_seconds,
        }

        return jwt.encode(
            payload,
            self._private_key,
            algorithm="ES256",
            headers={
                "kid": self.settings.signing_kid,
                "typ": AI_TENANT_CONTEXT_ASSERTION_TYP,
            },
        )

    def issue_internal_service_assertion(
        self,
    ) -> str:
        """Issue a service-only assertion for Gateway -> Core calls."""
        now = int(
            time.time()
        )

        payload = {
            "iss":
                self.settings.issuer,
            "aud":
                self.settings.service_audience,
            "sub":
                "identity-gateway",
            "purpose":
                "preauth",
            "jti":
                str(uuid4()),
            "iat":
                now,
            "nbf":
                now,
            "exp":
                (
                    now
                    + self.settings.
                    assertion_lifetime_seconds
                ),
        }

        return jwt.encode(
            payload,
            self._private_key,
            algorithm="ES256",
            headers={
                "kid":
                    self.settings.signing_kid,
                "typ":
                    INTERNAL_SERVICE_ASSERTION_TYP,
            },
        )

    def issue_internal_assertion(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> str:
        now = int(
            time.time()
        )

        payload = {
            "iss":
                self.settings.issuer,
            "aud":
                self.settings.audience,
            "sub":
                str(membership_id),
            "tenant_id":
                str(tenant_id),
            "jti":
                str(uuid4()),
            "iat":
                now,
            "nbf":
                now,
            "exp":
                (
                    now
                    + self.settings.
                    assertion_lifetime_seconds
                ),
        }

        return jwt.encode(
            payload,
            self._private_key,
            algorithm="ES256",
            headers={
                "kid":
                    self.settings.signing_kid,
                "typ":
                    INTERNAL_ASSERTION_TYP,
            },
        )
