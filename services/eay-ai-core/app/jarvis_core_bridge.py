from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .tool_contracts import ToolName, build_tool_plan

JARVIS_SERVICE_ASSERTION_TYP = "opex-jarvis-service+jwt"
JARVIS_SERVICE_ASSERTION_HEADER = "X-OPEX-Jarvis-Service-Assertion"
JARVIS_SERVICE_SUBJECT = "eay-ai-core"
JARVIS_SERVICE_PURPOSE = "jarvis-tool-execution"
DEFAULT_JARVIS_SERVICE_ISSUER = "eay-ai-core"
DEFAULT_JARVIS_SERVICE_AUDIENCE = "opex-core-jarvis"
DEFAULT_CORE_BASE_URL = "http://core-api:8000"
DEFAULT_ASSERTION_LIFETIME_SECONDS = 30
DEFAULT_CORE_TIMEOUT_SECONDS = 4.0
MAX_PRIVATE_KEY_BYTES = 64 * 1024
KID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

Environment = Literal["development", "test", "staging", "production"]


class JarvisCoreBridgeError(RuntimeError):
    """Base error for the EAY AI Core -> Platform Core authorization bridge."""


class JarvisCoreBridgeConfigurationError(JarvisCoreBridgeError):
    """Bridge configuration or private signing material is invalid."""


class JarvisCoreAuthorizationDenied(JarvisCoreBridgeError):
    """Platform Core did not authorize the invocation."""


class JarvisCoreAuthorizationUnavailable(JarvisCoreBridgeError):
    """Platform Core authorization authority cannot be reached safely."""


class JarvisCoreAuthorizationProtocolError(JarvisCoreBridgeError):
    """Platform Core returned an invalid or widened authorization context."""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise JarvisCoreBridgeConfigurationError(f"{name} must be a boolean")


def _normalized_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise JarvisCoreBridgeConfigurationError("Jarvis Core base URL is invalid")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise JarvisCoreBridgeConfigurationError("Jarvis Core base URL contains forbidden components")
    if parsed.path not in {"", "/"}:
        raise JarvisCoreBridgeConfigurationError("Jarvis Core base URL must not contain a path")
    return candidate


@dataclass(frozen=True)
class JarvisCoreBridgeSettings:
    environment: Environment
    enabled: bool
    core_base_url: str
    signing_key_file: str
    signing_kid: str
    assertion_issuer: str = DEFAULT_JARVIS_SERVICE_ISSUER
    assertion_audience: str = DEFAULT_JARVIS_SERVICE_AUDIENCE
    assertion_lifetime_seconds: int = DEFAULT_ASSERTION_LIFETIME_SECONDS
    timeout_seconds: float = DEFAULT_CORE_TIMEOUT_SECONDS

    @classmethod
    def from_environment(cls) -> "JarvisCoreBridgeSettings":
        environment_raw = os.getenv("EAY_AI_ENVIRONMENT", "development").strip().lower()
        if environment_raw not in {"development", "test", "staging", "production"}:
            raise JarvisCoreBridgeConfigurationError("EAY_AI_ENVIRONMENT is invalid")

        try:
            lifetime = int(
                os.getenv(
                    "EAY_JARVIS_SERVICE_ASSERTION_LIFETIME_SECONDS",
                    str(DEFAULT_ASSERTION_LIFETIME_SECONDS),
                )
            )
            timeout_seconds = float(
                os.getenv(
                    "EAY_JARVIS_CORE_TIMEOUT_SECONDS",
                    str(DEFAULT_CORE_TIMEOUT_SECONDS),
                )
            )
        except ValueError as exc:
            raise JarvisCoreBridgeConfigurationError(
                "Jarvis Core numeric configuration is invalid"
            ) from exc

        settings = cls(
            environment=environment_raw,  # type: ignore[arg-type]
            enabled=_env_bool("EAY_JARVIS_CORE_BRIDGE_ENABLED", False),
            core_base_url=_normalized_base_url(
                os.getenv("EAY_JARVIS_CORE_BASE_URL", DEFAULT_CORE_BASE_URL)
            ),
            signing_key_file=os.getenv("EAY_JARVIS_SERVICE_SIGNING_KEY_FILE", "").strip(),
            signing_kid=os.getenv("EAY_JARVIS_SERVICE_SIGNING_KID", "").strip(),
            assertion_issuer=os.getenv(
                "EAY_JARVIS_SERVICE_ASSERTION_ISSUER",
                DEFAULT_JARVIS_SERVICE_ISSUER,
            ).strip(),
            assertion_audience=os.getenv(
                "EAY_JARVIS_SERVICE_ASSERTION_AUDIENCE",
                DEFAULT_JARVIS_SERVICE_AUDIENCE,
            ).strip(),
            assertion_lifetime_seconds=lifetime,
            timeout_seconds=timeout_seconds,
        )
        settings.validate()
        return settings

    @property
    def production_like(self) -> bool:
        return self.environment in {"staging", "production"}

    def validate(self) -> None:
        if os.getenv("EAY_JARVIS_SERVICE_SIGNING_KEY", "").strip():
            raise JarvisCoreBridgeConfigurationError(
                "Jarvis private signing material must not be supplied through environment variables"
            )
        if not self.assertion_issuer or self.assertion_issuer == "opex-identity-gateway":
            raise JarvisCoreBridgeConfigurationError("Jarvis service issuer is invalid")
        if self.assertion_audience in {"", "opex-core-api", "opex-core-preauth"}:
            raise JarvisCoreBridgeConfigurationError("Jarvis service audience is invalid")
        if not 15 <= self.assertion_lifetime_seconds <= 60:
            raise JarvisCoreBridgeConfigurationError(
                "Jarvis assertion lifetime must be between 15 and 60 seconds"
            )
        if not 0.5 <= self.timeout_seconds <= 15.0:
            raise JarvisCoreBridgeConfigurationError("Jarvis Core timeout is invalid")
        if not self.enabled:
            return
        if not KID_PATTERN.fullmatch(self.signing_kid):
            raise JarvisCoreBridgeConfigurationError("Jarvis signing key identifier is invalid")
        path = Path(self.signing_key_file)
        try:
            file_stat = path.stat()
        except OSError as exc:
            raise JarvisCoreBridgeConfigurationError("Jarvis signing key is unavailable") from exc
        if not path.is_file() or file_stat.st_size <= 0 or file_stat.st_size > MAX_PRIVATE_KEY_BYTES:
            raise JarvisCoreBridgeConfigurationError("Jarvis signing key file is invalid")
        if self.production_like and os.name != "nt":
            unsafe_bits = stat.S_IRWXG | stat.S_IRWXO
            if file_stat.st_mode & unsafe_bits:
                raise JarvisCoreBridgeConfigurationError(
                    "Jarvis signing key file must not be accessible by group or others"
                )


class JarvisServiceAssertionSigner:
    """Issue narrowly scoped, short-lived service assertions for Platform Core."""

    def __init__(self, settings: JarvisCoreBridgeSettings) -> None:
        settings.validate()
        if not settings.enabled:
            raise JarvisCoreBridgeConfigurationError("Jarvis Core bridge is disabled")
        self.settings = settings
        self._private_key = self._load_private_key()

    def _load_private_key(self) -> ec.EllipticCurvePrivateKey:
        path = Path(self.settings.signing_key_file)
        try:
            key_bytes = path.read_bytes()
            key = serialization.load_pem_private_key(key_bytes, password=None)
        except Exception as exc:
            raise JarvisCoreBridgeConfigurationError("Jarvis signing key cannot be loaded") from exc
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise JarvisCoreBridgeConfigurationError("Jarvis signing key must be EC")
        if not isinstance(key.curve, ec.SECP256R1):
            raise JarvisCoreBridgeConfigurationError("Jarvis signing key must use P-256")
        return key

    def issue_assertion(self) -> str:
        now = int(time.time())
        claims = {
            "iss": self.settings.assertion_issuer,
            "aud": self.settings.assertion_audience,
            "sub": JARVIS_SERVICE_SUBJECT,
            "purpose": JARVIS_SERVICE_PURPOSE,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + self.settings.assertion_lifetime_seconds,
        }
        return jwt.encode(
            claims,
            self._private_key,
            algorithm="ES256",
            headers={
                "kid": self.settings.signing_kid,
                "typ": JARVIS_SERVICE_ASSERTION_TYP,
            },
        )

    def public_jwks(self) -> dict[str, object]:
        public_jwk = json.loads(ECAlgorithm.to_jwk(self._private_key.public_key()))
        public_jwk.update(
            {
                "kid": self.settings.signing_kid,
                "use": "sig",
                "alg": "ES256",
            }
        )
        if "d" in public_jwk:
            raise JarvisCoreBridgeConfigurationError("Public JWKS contains private material")
        return {"keys": [public_jwk]}


def _validate_json_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JarvisCoreAuthorizationProtocolError(f"Non-finite tool argument at {path}")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise JarvisCoreAuthorizationProtocolError(f"Non-string tool argument key at {path}")
            _validate_json_value(child, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _validate_json_value(child, path=f"{path}[{index}]")
        return
    raise JarvisCoreAuthorizationProtocolError(f"Unsupported tool argument at {path}")


def canonical_arguments_sha256(arguments: Mapping[str, Any]) -> str:
    _validate_json_value(arguments, path="$")
    try:
        encoded = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JarvisCoreAuthorizationProtocolError("Tool arguments are not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def canonical_reason_sha256(reason: str) -> str:
    normalized = " ".join(reason.split())
    if not normalized or len(normalized) > 1000:
        raise JarvisCoreAuthorizationProtocolError("Tool execution reason is invalid")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class TrustedCoreExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1, max_length=128)
    tenant_id: UUID
    actor_subject: str = Field(min_length=1, max_length=255)
    tool: ToolName
    granted_scopes: tuple[str, ...]
    authorization_fingerprint: str
    arguments_sha256: str
    reason_sha256: str

    @field_validator(
        "authorization_fingerprint",
        "arguments_sha256",
        "reason_sha256",
    )
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("invalid_sha256")
        return value


class JarvisCoreAuthorizationClient:
    """Consume one user grant through Platform Core. No automatic retries."""

    def __init__(
        self,
        settings: JarvisCoreBridgeSettings,
        *,
        signer: JarvisServiceAssertionSigner | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings.validate()
        if not settings.enabled:
            raise JarvisCoreBridgeConfigurationError("Jarvis Core bridge is disabled")
        self.settings = settings
        self.signer = signer or JarvisServiceAssertionSigner(settings)
        self._client = client

    def authorize(
        self,
        *,
        grant_token: SecretStr,
        tool: ToolName,
        arguments: dict[str, Any],
        reason: str,
    ) -> TrustedCoreExecutionContext:
        token = grant_token.get_secret_value()
        if len(token) < 32 or len(token) > 256 or any(ch.isspace() for ch in token):
            raise JarvisCoreAuthorizationDenied("AI tool grant is invalid")

        assertion = self.signer.issue_assertion()
        url = self.settings.core_base_url + "/internal/ai/tool-executions/authorize"
        request_body = {
            "grant_token": token,
            "tool": tool,
            "arguments": arguments,
            "reason": reason,
        }
        headers = {JARVIS_SERVICE_ASSERTION_HEADER: assertion}

        try:
            if self._client is not None:
                response = self._client.post(url, json=request_body, headers=headers)
            else:
                with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                    response = client.post(url, json=request_body, headers=headers)
        except httpx.HTTPError as exc:
            raise JarvisCoreAuthorizationUnavailable(
                "Platform Core authorization is unavailable"
            ) from exc

        if response.status_code in {400, 401, 403, 404}:
            raise JarvisCoreAuthorizationDenied("Platform Core denied tool authorization")
        if response.status_code != 200:
            raise JarvisCoreAuthorizationUnavailable(
                "Platform Core authorization is unavailable"
            )

        try:
            context = TrustedCoreExecutionContext.model_validate(response.json())
        except Exception as exc:
            raise JarvisCoreAuthorizationProtocolError(
                "Platform Core authorization response is invalid"
            ) from exc

        expected_plan = build_tool_plan(tool, arguments)
        expected_scopes = tuple(sorted(expected_plan.required_scope))
        expected_arguments_hash = canonical_arguments_sha256(arguments)
        expected_reason_hash = canonical_reason_sha256(reason)

        if context.tool != tool:
            raise JarvisCoreAuthorizationProtocolError("Platform Core changed tool identity")
        if tuple(sorted(context.granted_scopes)) != expected_scopes:
            raise JarvisCoreAuthorizationProtocolError("Platform Core returned widened tool scopes")
        if not secrets.compare_digest(context.arguments_sha256, expected_arguments_hash):
            raise JarvisCoreAuthorizationProtocolError("Platform Core argument binding mismatch")
        if not secrets.compare_digest(context.reason_sha256, expected_reason_hash):
            raise JarvisCoreAuthorizationProtocolError("Platform Core reason binding mismatch")

        return context
