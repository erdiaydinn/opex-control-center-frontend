"""At-most-once Platform Core -> EAY AI Core execution broker.

The browser never receives the opaque Redis tool grant. Platform Core derives
DB-backed capability, records a durable request audit, issues one short-lived
grant, and sends it exactly once over the internal AI plane.
"""

from __future__ import annotations

import json
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.ai_tool_authorization import TOOL_REQUIRED_SCOPES, AiToolName
from app.core.jarvis_safety_policy import ToolExecutionEnvelope

AI_CORE_EXECUTION_PATH = "/v1/tool-execution"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class JarvisExecutionBrokerError(RuntimeError):
    """Base class for governed AI Core broker failures."""


class JarvisExecutionBrokerUnavailable(JarvisExecutionBrokerError):
    """Broker is disabled or cannot safely reach AI Core."""


class JarvisExecutionBrokerDenied(JarvisExecutionBrokerError):
    """AI Core/Platform authorization rejected this invocation."""


class JarvisExecutionBrokerIndeterminate(JarvisExecutionBrokerError):
    """The grant may have been consumed; never retry it automatically."""


class JarvisExecutionBrokerContractError(JarvisExecutionBrokerError):
    """AI Core response violated the reviewed cross-service contract."""


class JarvisExecutionBrokerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPEX_JARVIS_BROKER_",
        case_sensitive=False,
        extra="ignore",
    )

    enabled: bool = False
    ai_core_base_url: str = "http://eay-ai-core:8030"
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=130)
    tool_timeout_ms: int = Field(default=20_000, ge=1000, le=120_000)
    maximum_bytes_billed: int = Field(
        default=250 * 1024 * 1024,
        ge=1,
        le=10 * 1024 * 1024 * 1024,
    )
    max_rows: int = Field(default=500, ge=1, le=500)
    max_response_bytes: int = Field(
        default=2 * 1024 * 1024,
        ge=64 * 1024,
        le=8 * 1024 * 1024,
    )

    @model_validator(mode="after")
    def validate_broker_boundary(self) -> JarvisExecutionBrokerSettings:
        base_url = self.ai_core_base_url.strip().rstrip("/")
        parsed = urlsplit(base_url)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Jarvis AI Core base URL is invalid")

        minimum_timeout = (self.tool_timeout_ms / 1000) + 5
        if self.request_timeout_seconds < minimum_timeout:
            raise ValueError(
                "Jarvis broker timeout must cover the server-owned tool timeout"
            )

        object.__setattr__(self, "ai_core_base_url", base_url)
        return self


class BrokerExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_id: str = Field(min_length=1, max_length=128)
    status: Literal["executed", "rejected_cost"]
    dry_run_bytes: int = Field(ge=0)
    maximum_bytes_billed: int = Field(ge=1)
    row_count: int = Field(default=0, ge=0, le=500)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    sql_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_rows(self) -> BrokerExecutionResult:
        if self.row_count != len(self.rows):
            raise ValueError("AI Core row count does not match rows")
        if self.status == "rejected_cost" and self.rows:
            raise ValueError("Rejected AI Core execution must not return rows")
        return self


class BrokerToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: AiToolName
    query_id: str = Field(min_length=1, max_length=180)
    required_scope: tuple[str, ...]
    execution: BrokerExecutionResult
    legal_grounding: dict[str, Any] | None = None
    semantic_verification: dict[str, Any] | None = None
    schema_verification: dict[str, Any] | None = None
    runtime_activation: dict[str, Any] | None = None
    activation_provenance_fingerprint: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    result_contract_fingerprint: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    model_authored_sql_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_authorized_contract(self) -> BrokerToolExecutionResult:
        expected = tuple(sorted(TOOL_REQUIRED_SCOPES[self.tool]))
        if tuple(sorted(self.required_scope)) != expected:
            raise ValueError("AI Core returned unexpected tool scopes")
        if self.execution.row_count > 500:
            raise ValueError("AI Core returned too many rows")
        return self


class JarvisExecutionBroker:
    """Send one grant to AI Core exactly once and strictly validate result."""

    def __init__(
        self,
        settings: JarvisExecutionBrokerSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    def require_enabled(self) -> None:
        if not self._settings.enabled:
            raise JarvisExecutionBrokerUnavailable(
                "Jarvis execution broker is disabled"
            )

    def _validate_execution_envelope(
        self,
        *,
        tool: AiToolName,
        execution_policy: ToolExecutionEnvelope,
    ) -> None:
        if execution_policy.tool != tool:
            raise JarvisExecutionBrokerContractError(
                "Jarvis safety envelope tool does not match"
            )
        if execution_policy.side_effect_class not in {"none", "read"}:
            raise JarvisExecutionBrokerContractError(
                "Jarvis broker refuses mutating safety envelopes"
            )
        if execution_policy.requires_human_approval:
            raise JarvisExecutionBrokerContractError(
                "Jarvis broker cannot bypass required human approval"
            )
        if execution_policy.risk_class == "critical":
            raise JarvisExecutionBrokerContractError(
                "Jarvis broker refuses critical auto-execution"
            )
        if execution_policy.maximum_bytes_billed > self._settings.maximum_bytes_billed:
            raise JarvisExecutionBrokerContractError(
                "Jarvis safety byte budget exceeds broker ceiling"
            )
        if execution_policy.timeout_ms > self._settings.tool_timeout_ms:
            raise JarvisExecutionBrokerContractError(
                "Jarvis safety timeout exceeds broker ceiling"
            )
        if execution_policy.max_rows > self._settings.max_rows:
            raise JarvisExecutionBrokerContractError(
                "Jarvis safety row budget exceeds broker ceiling"
            )

    async def execute(
        self,
        *,
        grant_token: str,
        tool: AiToolName,
        arguments: dict[str, Any],
        reason: str,
        execution_policy: ToolExecutionEnvelope,
    ) -> BrokerToolExecutionResult:
        self.require_enabled()
        self._validate_execution_envelope(
            tool=tool,
            execution_policy=execution_policy,
        )

        if not isinstance(grant_token, str) or not 32 <= len(grant_token) <= 256:
            raise JarvisExecutionBrokerContractError(
                "Jarvis execution grant is invalid"
            )

        payload = {
            "tool": tool,
            "arguments": arguments,
            "grant_token": grant_token,
            "reason": reason,
            "execute": True,
            "maximum_bytes_billed": execution_policy.maximum_bytes_billed,
            "timeout_ms": execution_policy.timeout_ms,
            "max_rows": execution_policy.max_rows,
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self._settings.ai_core_base_url,
            timeout=self._settings.request_timeout_seconds,
        )

        try:
            try:
                async with client.stream(
                    "POST",
                    AI_CORE_EXECUTION_PATH,
                    json=payload,
                ) as response:
                    status_code = response.status_code

                    if status_code in {401, 403}:
                        raise JarvisExecutionBrokerDenied(
                            "AI Core rejected the governed invocation"
                        )

                    if status_code in {408, 425, 429, 500, 502, 503, 504}:
                        raise JarvisExecutionBrokerIndeterminate(
                            "AI Core execution outcome is unknown; do not retry grant"
                        )

                    if status_code in {400, 409, 422}:
                        raise JarvisExecutionBrokerContractError(
                            "AI Core rejected the broker execution contract"
                        )

                    if status_code != 200:
                        raise JarvisExecutionBrokerContractError(
                            "Unexpected AI Core execution status"
                        )

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._settings.max_response_bytes:
                            raise JarvisExecutionBrokerIndeterminate(
                                "AI Core response exceeded broker safety limit"
                            )
            except JarvisExecutionBrokerError:
                raise
            except httpx.HTTPError as exc:
                raise JarvisExecutionBrokerIndeterminate(
                    "AI Core execution outcome is unknown; do not retry grant"
                ) from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            raw = json.loads(body.decode("utf-8"))
            result = BrokerToolExecutionResult.model_validate(raw)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise JarvisExecutionBrokerContractError(
                "AI Core execution response is invalid"
            ) from exc

        if result.tool != tool:
            raise JarvisExecutionBrokerContractError(
                "AI Core returned a different tool"
            )
        if result.execution.maximum_bytes_billed != execution_policy.maximum_bytes_billed:
            raise JarvisExecutionBrokerContractError(
                "AI Core changed the server-owned byte budget"
            )
        if result.execution.row_count > execution_policy.max_rows:
            raise JarvisExecutionBrokerContractError(
                "AI Core exceeded the server-owned row budget"
            )

        return result
