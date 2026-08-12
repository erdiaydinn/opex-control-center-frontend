"""At-most-once Platform Core authorization client for Jarvis tools.

The AI Core sends only an opaque user-issued grant plus the exact reviewed
tool invocation. Tenant, actor identity and permission scopes are recovered by
Platform Core from the trusted grant record and are never caller supplied.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .jarvis_service_identity import JarvisServiceIdentitySigner
from .tool_contracts import SCOPES, ToolPlan

JARVIS_SERVICE_ASSERTION_HEADER = "X-OPEX-Jarvis-Service-Assertion"
AUTHORIZATION_PATH = "/internal/ai/tool-executions/authorize"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class PlatformToolAuthorizationError(RuntimeError):
    """Base class for Platform Core tool authorization failures."""


class PlatformToolAuthorizationDenied(PlatformToolAuthorizationError):
    """The grant or invocation was rejected and must not be retried."""


class PlatformToolAuthorizationIndeterminate(
    PlatformToolAuthorizationError
):
    """Grant consumption may have occurred; never retry the same grant."""


class PlatformToolAuthorizationContractError(
    PlatformToolAuthorizationError
):
    """Platform response violated the reviewed execution contract."""


class TrustedToolExecutionContext(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    request_id: str = Field(
        min_length=1,
        max_length=128,
    )
    tenant_id: UUID
    actor_subject: str = Field(
        min_length=1,
        max_length=512,
    )
    tool: str
    granted_scopes: tuple[str, ...]
    authorization_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )
    arguments_sha256: str = Field(
        pattern=SHA256_PATTERN
    )
    reason_sha256: str = Field(
        pattern=SHA256_PATTERN
    )


@dataclass(frozen=True)
class PlatformToolAuthorizerSettings:
    base_url: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")

        if not base_url:
            raise ValueError(
                "Platform Core base URL is required"
            )

        if not (
            base_url.startswith("http://")
            or base_url.startswith("https://")
        ):
            raise ValueError(
                "Platform Core base URL must be HTTP(S)"
            )

        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0 < float(self.timeout_seconds) <= 30
        ):
            raise ValueError(
                "Platform Core authorization timeout is invalid"
            )

        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(
            self,
            "timeout_seconds",
            float(self.timeout_seconds),
        )


def _arguments_sha256(arguments: dict[str, Any]) -> str:
    encoded = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reason_sha256(reason: str) -> str:
    normalized = " ".join(reason.split())

    if not normalized or len(normalized) > 1000:
        raise ValueError(
            "Tool execution reason is invalid"
        )

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


class PlatformToolAuthorizer:
    """Authorize one reviewed tool invocation without automatic retries."""

    def __init__(
        self,
        settings: PlatformToolAuthorizerSettings,
        signer: JarvisServiceIdentitySigner,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._signer = signer
        self._client = client

    async def authorize(
        self,
        *,
        grant_token: str,
        plan: ToolPlan,
        reason: str,
    ) -> TrustedToolExecutionContext:
        if (
            not isinstance(grant_token, str)
            or not 32 <= len(grant_token) <= 256
        ):
            raise PlatformToolAuthorizationDenied(
                "AI tool grant is invalid"
            )

        if not plan.read_only or plan.model_authored_sql_allowed:
            raise PlatformToolAuthorizationContractError(
                "Tool plan is not safe for governed execution"
            )

        expected_scopes = tuple(
            sorted(SCOPES[plan.tool])
        )
        expected_arguments_sha256 = _arguments_sha256(
            plan.arguments
        )
        expected_reason_sha256 = _reason_sha256(reason)

        payload = {
            "grant_token": grant_token,
            "tool": plan.tool,
            "arguments": plan.arguments,
            "reason": reason,
        }

        # Fresh machine assertion for exactly this network attempt.
        # There is deliberately no retry loop: a timeout/503 may occur after
        # Platform Core has already consumed the user grant.
        assertion = (
            self._signer.issue_tool_execution_assertion()
        )
        headers = {
            JARVIS_SERVICE_ASSERTION_HEADER: assertion,
            "Content-Type": "application/json",
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self._settings.base_url,
            timeout=self._settings.timeout_seconds,
        )

        try:
            try:
                response = await client.post(
                    AUTHORIZATION_PATH,
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                raise PlatformToolAuthorizationIndeterminate(
                    "Platform authorization outcome is unknown; "
                    "do not retry this grant"
                ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code == 401:
            raise PlatformToolAuthorizationDenied(
                "Platform rejected the grant or invocation"
            )

        if response.status_code in {
            408,
            425,
            429,
            500,
            502,
            503,
            504,
        }:
            raise PlatformToolAuthorizationIndeterminate(
                "Platform authorization may have consumed the grant; "
                "do not retry this grant"
            )

        if response.status_code != 200:
            raise PlatformToolAuthorizationContractError(
                f"Unexpected Platform authorization status: "
                f"{response.status_code}"
            )

        try:
            context = TrustedToolExecutionContext.model_validate(
                response.json()
            )
        except (ValueError, ValidationError) as exc:
            raise PlatformToolAuthorizationContractError(
                "Platform authorization response is invalid"
            ) from exc

        if not REQUEST_ID_PATTERN.fullmatch(context.request_id):
            raise PlatformToolAuthorizationContractError(
                "Platform request ID is invalid"
            )

        if context.tool != plan.tool:
            raise PlatformToolAuthorizationContractError(
                "Platform authorized a different tool"
            )

        if tuple(sorted(context.granted_scopes)) != expected_scopes:
            raise PlatformToolAuthorizationContractError(
                "Platform authorized unexpected scopes"
            )

        if context.arguments_sha256 != expected_arguments_sha256:
            raise PlatformToolAuthorizationContractError(
                "Platform authorized different arguments"
            )

        if context.reason_sha256 != expected_reason_sha256:
            raise PlatformToolAuthorizationContractError(
                "Platform authorized a different execution reason"
            )

        return context
