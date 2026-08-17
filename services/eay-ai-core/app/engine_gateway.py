"""Executable intelligence-engine gateway for EAY Jarvis.

The gateway makes the intelligence router operational without weakening its
privacy/risk boundary. Callers submit a task and prompt; the gateway recomputes
routing from registered engine profiles and invokes only the selected verified
engine. A caller cannot supply a forged routing plan.

Supported adapters in v1:
- Ollama `/api/chat`, preserving the existing local-first EAY path.
- OpenAI Responses API `/v1/responses` as a default-disabled frontier engine.

The OpenAI adapter deliberately uses `store=false`, does not enable provider
built-in tools or background mode, and never returns the API key or prompt in
its receipt. Tool execution remains under EAY policy/capability governance.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, model_validator

from .intelligence_router import (
    IntelligenceEngine,
    IntelligenceRoutingPlan,
    IntelligenceTask,
    PrivacyLevel,
    route_intelligence,
)

ENGINE_GATEWAY_CONTRACT = "eay-engine-gateway-v1"


class EngineProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI_RESPONSES = "openai_responses"


class EngineEndpoint(BaseModel):
    engine_id: str = Field(min_length=1)
    provider: EngineProvider
    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=8)
    secret_ref: str | None = None
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    allow_remote_local_engine: bool = False

    @model_validator(mode="after")
    def endpoint_boundary(self) -> "EngineEndpoint":
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if not host:
            raise ValueError("engine_endpoint_host_required")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("engine_endpoint_url_credentials_or_fragment_forbidden")

        if self.provider is EngineProvider.OLLAMA:
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("ollama_endpoint_http_required")
            if not self.allow_remote_local_engine and host not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("ollama_remote_endpoint_requires_explicit_authorization")
            if self.secret_ref is not None:
                raise ValueError("ollama_local_adapter_does_not_accept_secret_ref")
        elif self.provider is EngineProvider.OPENAI_RESPONSES:
            if parsed.scheme != "https":
                raise ValueError("openai_endpoint_https_required")
            if host != "api.openai.com":
                raise ValueError("openai_endpoint_host_must_be_official")
            if not self.secret_ref:
                raise ValueError("openai_secret_ref_required")
        return self


class RegisteredEngine(BaseModel):
    profile: IntelligenceEngine
    endpoint: EngineEndpoint

    @model_validator(mode="after")
    def ids_and_locality_match(self) -> "RegisteredEngine":
        if self.profile.engine_id != self.endpoint.engine_id:
            raise ValueError("engine_profile_endpoint_id_mismatch")
        if self.endpoint.provider is EngineProvider.OLLAMA and not self.profile.local_processing:
            raise ValueError("ollama_engine_profile_must_be_local")
        if self.endpoint.provider is EngineProvider.OPENAI_RESPONSES and self.profile.local_processing:
            raise ValueError("openai_engine_profile_cannot_claim_local_processing")
        return self


class EngineInvocationReceipt(BaseModel):
    contract: str = ENGINE_GATEWAY_CONTRACT
    task_id: str
    engine_id: str
    provider: EngineProvider
    model_id: str
    output_text: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    provider_response_id: str | None = None
    provider_stored_state_requested: bool = False
    provider_tools_enabled: bool = False
    prompt_retained: bool = False
    secret_retained: bool = False
    external_processing: bool
    routing_plan: IntelligenceRoutingPlan

    @model_validator(mode="after")
    def receipt_preserves_gateway_boundaries(self) -> "EngineInvocationReceipt":
        if self.provider_stored_state_requested:
            raise ValueError("engine_gateway_cannot_request_provider_state_storage")
        if self.provider_tools_enabled:
            raise ValueError("engine_gateway_v1_cannot_enable_provider_tools")
        if self.prompt_retained or self.secret_retained:
            raise ValueError("engine_gateway_receipt_cannot_retain_prompt_or_secret")
        return self


class EngineGatewayError(RuntimeError):
    pass


def _resolve_env_secret(secret_ref: str | None, environ: dict[str, str]) -> str:
    if not secret_ref or not secret_ref.startswith("env:"):
        raise EngineGatewayError("engine_secret_ref_must_use_env_scheme")
    key = secret_ref.removeprefix("env:").strip()
    if not key:
        raise EngineGatewayError("engine_secret_env_name_missing")
    value = environ.get(key, "")
    if not value:
        raise EngineGatewayError("engine_secret_not_available")
    return value


def _extract_openai_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "".join(parts).strip()


def _safe_usage_int(payload: dict[str, Any], key: str) -> int | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    return value if isinstance(value, int) and value >= 0 else None


class EngineGateway:
    def __init__(
        self,
        registrations: list[RegisteredEngine],
        *,
        transport_factory: Callable[[EngineEndpoint], httpx.AsyncBaseTransport | None] | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        ids = [item.profile.engine_id for item in registrations]
        if len(ids) != len(set(ids)):
            raise ValueError("engine_gateway_duplicate_engine_id")
        self._registrations = {item.profile.engine_id: item for item in registrations}
        self._transport_factory = transport_factory
        self._environ = dict(os.environ if environ is None else environ)

    def plan(self, task: IntelligenceTask) -> IntelligenceRoutingPlan:
        return route_intelligence(task, [item.profile for item in self._registrations.values()])

    async def invoke_primary(self, *, task: IntelligenceTask, prompt: str) -> EngineInvocationReceipt:
        if not prompt.strip():
            raise ValueError("engine_gateway_prompt_required")
        plan = self.plan(task)
        if not plan.execution_permitted or not plan.primary_engine_id:
            raise EngineGatewayError("engine_routing_plan_not_executable:" + ",".join(plan.blockers))
        registration = self._registrations[plan.primary_engine_id]
        endpoint = registration.endpoint

        if endpoint.provider is EngineProvider.OPENAI_RESPONSES:
            if task.privacy in {PrivacyLevel.CONFIDENTIAL, PrivacyLevel.RESTRICTED} and not task.external_processing_authorized:
                raise EngineGatewayError("external_processing_not_authorized_for_sensitive_task")
            return await self._invoke_openai(task=task, prompt=prompt, plan=plan, registration=registration)
        return await self._invoke_ollama(task=task, prompt=prompt, plan=plan, registration=registration)

    def _transport(self, endpoint: EngineEndpoint) -> httpx.AsyncBaseTransport | None:
        return self._transport_factory(endpoint) if self._transport_factory else None

    async def _invoke_ollama(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        plan: IntelligenceRoutingPlan,
        registration: RegisteredEngine,
    ) -> EngineInvocationReceipt:
        endpoint = registration.endpoint
        payload = {
            "model": endpoint.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        async with httpx.AsyncClient(
            timeout=endpoint.timeout_seconds,
            transport=self._transport(endpoint),
        ) as client:
            response = await client.post(endpoint.base_url.rstrip("/") + "/api/chat", json=payload)
            response.raise_for_status()
            raw = response.json()
        text = raw.get("message", {}).get("content", "") if isinstance(raw, dict) else ""
        if not isinstance(text, str) or not text.strip():
            raise EngineGatewayError("ollama_response_text_missing")
        prompt_tokens = raw.get("prompt_eval_count") if isinstance(raw, dict) else None
        output_tokens = raw.get("eval_count") if isinstance(raw, dict) else None
        return EngineInvocationReceipt(
            task_id=task.task_id,
            engine_id=registration.profile.engine_id,
            provider=endpoint.provider,
            model_id=endpoint.model_id,
            output_text=text.strip(),
            input_tokens=prompt_tokens if isinstance(prompt_tokens, int) and prompt_tokens >= 0 else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) and output_tokens >= 0 else None,
            external_processing=False,
            routing_plan=plan,
        )

    async def _invoke_openai(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        plan: IntelligenceRoutingPlan,
        registration: RegisteredEngine,
    ) -> EngineInvocationReceipt:
        endpoint = registration.endpoint
        secret = _resolve_env_secret(endpoint.secret_ref, self._environ)
        payload = {
            "model": endpoint.model_id,
            "input": prompt,
            "store": False,
            "max_output_tokens": endpoint.max_output_tokens,
        }
        headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=endpoint.timeout_seconds,
            transport=self._transport(endpoint),
        ) as client:
            response = await client.post(endpoint.base_url.rstrip("/") + "/v1/responses", headers=headers, json=payload)
            response.raise_for_status()
            raw = response.json()
        if not isinstance(raw, dict):
            raise EngineGatewayError("openai_response_not_object")
        text = _extract_openai_text(raw)
        if not text:
            raise EngineGatewayError("openai_response_text_missing")
        return EngineInvocationReceipt(
            task_id=task.task_id,
            engine_id=registration.profile.engine_id,
            provider=endpoint.provider,
            model_id=endpoint.model_id,
            output_text=text,
            input_tokens=_safe_usage_int(raw, "input_tokens"),
            output_tokens=_safe_usage_int(raw, "output_tokens"),
            provider_response_id=raw.get("id") if isinstance(raw.get("id"), str) else None,
            external_processing=True,
            routing_plan=plan,
        )
