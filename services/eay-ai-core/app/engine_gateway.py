"""Executable intelligence-engine gateway for EAY Jarvis.

The gateway makes the intelligence router operational without weakening its
privacy/risk boundary. Normal callers submit a task and prompt and the gateway
recomputes routing from registered, verified production engines. A separate
benchmark-only mode can invoke one exact-adapter-verified candidate before
promotion, but only for tool-free reasoning and under the same privacy/risk/
modality boundary. That breaks the benchmark/promotion circular dependency
without creating an execution backdoor.

Supported adapters:
- Ollama `/api/chat`, preserving the existing local-first EAY path.
- OpenAI Responses API `/v1/responses`.
- Anthropic Messages API `/v1/messages`.
- Google Gemini `generateContent` REST API.

Provider built-in tools are not enabled, secrets and prompts are not returned
in receipts, and provider HTTP/transport errors are reduced to status/type-only
EAY errors so request state cannot leak through exception chains.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Callable
from urllib.parse import quote, urlparse

import httpx
from pydantic import BaseModel, Field, model_validator

from .intelligence_router import (
    IntelligenceEngine,
    IntelligenceRoutingPlan,
    IntelligenceTask,
    PrivacyLevel,
    engine_satisfies_task_boundary,
    route_intelligence,
)

ENGINE_GATEWAY_CONTRACT = "eay-engine-gateway-v2"


class EngineProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI_RESPONSES = "openai_responses"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GEMINI_GENERATE_CONTENT = "gemini_generate_content"


class EngineInvocationMode(str, Enum):
    ROUTED = "routed"
    BENCHMARK = "benchmark"


_OFFICIAL_FRONTIER_HOSTS = {
    EngineProvider.OPENAI_RESPONSES: "api.openai.com",
    EngineProvider.ANTHROPIC_MESSAGES: "api.anthropic.com",
    EngineProvider.GEMINI_GENERATE_CONTENT: "generativelanguage.googleapis.com",
}


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
        if parsed.query:
            raise ValueError("engine_endpoint_base_query_forbidden")

        if self.provider is EngineProvider.OLLAMA:
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("ollama_endpoint_http_required")
            if not self.allow_remote_local_engine and host not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("ollama_remote_endpoint_requires_explicit_authorization")
            if self.secret_ref is not None:
                raise ValueError("ollama_local_adapter_does_not_accept_secret_ref")
        else:
            if parsed.scheme != "https":
                raise ValueError("frontier_endpoint_https_required")
            expected_host = _OFFICIAL_FRONTIER_HOSTS[self.provider]
            if host != expected_host:
                if self.provider is EngineProvider.OPENAI_RESPONSES:
                    raise ValueError("openai_endpoint_host_must_be_official")
                raise ValueError(f"{self.provider.value}_endpoint_host_must_be_official")
            if parsed.path not in {"", "/"}:
                raise ValueError("frontier_endpoint_base_path_must_be_root")
            if not self.secret_ref:
                raise ValueError("frontier_secret_ref_required")
        return self


class RegisteredEngine(BaseModel):
    profile: IntelligenceEngine
    endpoint: EngineEndpoint

    @model_validator(mode="after")
    def ids_and_locality_match(self) -> "RegisteredEngine":
        if self.profile.engine_id != self.endpoint.engine_id:
            raise ValueError("engine_profile_endpoint_id_mismatch")
        if self.endpoint.provider is EngineProvider.OLLAMA:
            if not self.profile.local_processing:
                raise ValueError("ollama_engine_profile_must_be_local")
        elif self.profile.local_processing:
            raise ValueError("frontier_engine_profile_cannot_claim_local_processing")
        return self


class BenchmarkInvocationContext(BaseModel):
    benchmark_run_ref: str = Field(pattern=r"^benchmark-run://[A-Za-z0-9._:/-]+$")
    engine_id: str = Field(min_length=1)
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_ref: str = Field(min_length=1)
    side_effects_authorized: bool = False

    @model_validator(mode="after")
    def benchmark_context_never_authorizes_side_effects(self) -> "BenchmarkInvocationContext":
        if self.side_effects_authorized:
            raise ValueError("engine_benchmark_context_never_authorizes_side_effects")
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
    invocation_mode: EngineInvocationMode = EngineInvocationMode.ROUTED
    benchmark_context_ref: str | None = None

    @model_validator(mode="after")
    def receipt_preserves_gateway_boundaries(self) -> "EngineInvocationReceipt":
        if self.provider_stored_state_requested:
            raise ValueError("engine_gateway_cannot_request_provider_state_storage")
        if self.provider_tools_enabled:
            raise ValueError("engine_gateway_cannot_enable_provider_tools")
        if self.prompt_retained or self.secret_retained:
            raise ValueError("engine_gateway_receipt_cannot_retain_prompt_or_secret")
        if self.invocation_mode is EngineInvocationMode.BENCHMARK and not self.benchmark_context_ref:
            raise ValueError("benchmark_engine_receipt_requires_context_ref")
        if self.invocation_mode is EngineInvocationMode.ROUTED and self.benchmark_context_ref is not None:
            raise ValueError("routed_engine_receipt_cannot_claim_benchmark_context")
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


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    return "".join(
        block.get("text", "")
        for block in payload.get("content", []) or []
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ).strip()


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates", []) or []
    if not candidates or not isinstance(candidates[0], dict):
        return ""
    content = candidates[0].get("content")
    if not isinstance(content, dict):
        return ""
    return "".join(
        part.get("text", "")
        for part in content.get("parts", []) or []
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ).strip()


def _safe_usage_int(payload: dict[str, Any], key: str, *, container: str = "usage") -> int | None:
    usage = payload.get(container)
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    return value if isinstance(value, int) and value >= 0 else None


async def _post_json_safely(
    *,
    provider: EngineProvider,
    url: str,
    headers: dict[str, str] | None,
    payload: dict[str, Any],
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
) -> Any:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, transport=transport) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise EngineGatewayError(
            f"{provider.value}_transport_error:{type(exc).__name__}"
        ) from None
    if not response.is_success:
        raise EngineGatewayError(
            f"{provider.value}_http_status:{response.status_code}"
        ) from None
    try:
        return response.json()
    except (ValueError, TypeError):
        raise EngineGatewayError(f"{provider.value}_response_json_invalid") from None


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
        return await self._invoke_registered(
            task=task,
            prompt=prompt,
            plan=plan,
            registration=self._registrations[plan.primary_engine_id],
        )

    async def invoke_routed_engines(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
    ) -> tuple[EngineInvocationReceipt, ...]:
        if not prompt.strip():
            raise ValueError("engine_gateway_prompt_required")
        plan = self.plan(task)
        if not plan.execution_permitted or not plan.primary_engine_id:
            raise EngineGatewayError("engine_routing_plan_not_executable:" + ",".join(plan.blockers))
        selected = (plan.primary_engine_id, *plan.critic_engine_ids)
        receipts: list[EngineInvocationReceipt] = []
        for engine_id in selected:
            receipts.append(
                await self._invoke_registered(
                    task=task,
                    prompt=prompt,
                    plan=plan,
                    registration=self._registrations[engine_id],
                )
            )
        return tuple(receipts)

    async def invoke_for_benchmark(
        self,
        *,
        engine_id: str,
        task: IntelligenceTask,
        prompt: str,
        context: BenchmarkInvocationContext,
    ) -> EngineInvocationReceipt:
        """Invoke one exact candidate for measured, tool-free pre-promotion evaluation."""

        if not prompt.strip():
            raise ValueError("engine_gateway_prompt_required")
        if context.engine_id != engine_id:
            raise EngineGatewayError("benchmark_context_engine_identity_mismatch")
        if task.requires_tools:
            raise EngineGatewayError("benchmark_engine_invocation_forbids_provider_tools")
        registration = self._registrations.get(engine_id)
        if registration is None:
            raise EngineGatewayError("benchmark_engine_not_registered")
        if not engine_satisfies_task_boundary(
            task,
            registration.profile,
            require_production_enabled=False,
        ):
            raise EngineGatewayError("benchmark_engine_does_not_satisfy_task_boundary")

        benchmark_plan = IntelligenceRoutingPlan(
            task_id=task.task_id,
            primary_engine_id=engine_id,
            execution_permitted=True,
        )
        receipt = await self._invoke_registered(
            task=task,
            prompt=prompt,
            plan=benchmark_plan,
            registration=registration,
        )
        return receipt.model_copy(
            update={
                "invocation_mode": EngineInvocationMode.BENCHMARK,
                "benchmark_context_ref": context.benchmark_run_ref,
            }
        )

    def _transport(self, endpoint: EngineEndpoint) -> httpx.AsyncBaseTransport | None:
        return self._transport_factory(endpoint) if self._transport_factory else None

    async def _invoke_registered(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        plan: IntelligenceRoutingPlan,
        registration: RegisteredEngine,
    ) -> EngineInvocationReceipt:
        endpoint = registration.endpoint
        if endpoint.provider is not EngineProvider.OLLAMA:
            if task.privacy in {PrivacyLevel.CONFIDENTIAL, PrivacyLevel.RESTRICTED} and not task.external_processing_authorized:
                raise EngineGatewayError("external_processing_not_authorized_for_sensitive_task")
        if endpoint.provider is EngineProvider.OPENAI_RESPONSES:
            return await self._invoke_openai(task=task, prompt=prompt, plan=plan, registration=registration)
        if endpoint.provider is EngineProvider.ANTHROPIC_MESSAGES:
            return await self._invoke_anthropic(task=task, prompt=prompt, plan=plan, registration=registration)
        if endpoint.provider is EngineProvider.GEMINI_GENERATE_CONTENT:
            return await self._invoke_gemini(task=task, prompt=prompt, plan=plan, registration=registration)
        return await self._invoke_ollama(task=task, prompt=prompt, plan=plan, registration=registration)

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
        raw = await _post_json_safely(
            provider=endpoint.provider,
            url=endpoint.base_url.rstrip("/") + "/api/chat",
            headers=None,
            payload=payload,
            timeout_seconds=endpoint.timeout_seconds,
            transport=self._transport(endpoint),
        )
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
        headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
        raw = await _post_json_safely(
            provider=endpoint.provider,
            url=endpoint.base_url.rstrip("/") + "/v1/responses",
            headers=headers,
            payload=payload,
            timeout_seconds=endpoint.timeout_seconds,
            transport=self._transport(endpoint),
        )
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

    async def _invoke_anthropic(
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
            "max_tokens": endpoint.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": secret,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        raw = await _post_json_safely(
            provider=endpoint.provider,
            url=endpoint.base_url.rstrip("/") + "/v1/messages",
            headers=headers,
            payload=payload,
            timeout_seconds=endpoint.timeout_seconds,
            transport=self._transport(endpoint),
        )
        if not isinstance(raw, dict):
            raise EngineGatewayError("anthropic_response_not_object")
        text = _extract_anthropic_text(raw)
        if not text:
            raise EngineGatewayError("anthropic_response_text_missing")
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

    async def _invoke_gemini(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        plan: IntelligenceRoutingPlan,
        registration: RegisteredEngine,
    ) -> EngineInvocationReceipt:
        endpoint = registration.endpoint
        secret = _resolve_env_secret(endpoint.secret_ref, self._environ)
        model_path = quote(endpoint.model_id, safe="-._")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": endpoint.max_output_tokens},
        }
        headers = {"x-goog-api-key": secret, "content-type": "application/json"}
        raw = await _post_json_safely(
            provider=endpoint.provider,
            url=endpoint.base_url.rstrip("/") + f"/v1beta/models/{model_path}:generateContent",
            headers=headers,
            payload=payload,
            timeout_seconds=endpoint.timeout_seconds,
            transport=self._transport(endpoint),
        )
        if not isinstance(raw, dict):
            raise EngineGatewayError("gemini_response_not_object")
        text = _extract_gemini_text(raw)
        if not text:
            raise EngineGatewayError("gemini_response_text_missing")
        return EngineInvocationReceipt(
            task_id=task.task_id,
            engine_id=registration.profile.engine_id,
            provider=endpoint.provider,
            model_id=endpoint.model_id,
            output_text=text,
            input_tokens=_safe_usage_int(raw, "promptTokenCount", container="usageMetadata"),
            output_tokens=_safe_usage_int(raw, "candidatesTokenCount", container="usageMetadata"),
            provider_response_id=raw.get("responseId") if isinstance(raw.get("responseId"), str) else None,
            external_processing=True,
            routing_plan=plan,
        )
