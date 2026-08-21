"""Fail-closed read-only runtime for governed Jarvis context providers.

The gateway decides whether a provider request is admissible. This runtime adds
an independent transport boundary: only executable gateway plans and exact,
code-reviewed adapter policies may reach the network. It never infers company
KPIs, causality, or execution authority from an external payload.
"""

from __future__ import annotations

import hashlib
import ipaddress
from datetime import UTC, datetime
from urllib.parse import parse_qsl, unquote, urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .context_provider_gateway import (
    CONTEXT_PROVIDER_GATEWAY_CONTRACT,
    SENSITIVE_QUERY_KEYS,
    ProviderRequestPlan,
    RequestPurpose,
)
from .context_provider_registry import ContextProviderSpec, require_provider

CONTEXT_PROVIDER_RUNTIME_CONTRACT = "eay-context-provider-runtime-v1"
MAX_RUNTIME_RESPONSE_BYTES = 5_000_000
MAX_RUNTIME_TIMEOUT_SECONDS = 20.0


class ProviderRuntimeBlocked(RuntimeError):
    """The request is not authorized to cross the external network boundary."""


class ProviderRuntimeUnavailable(RuntimeError):
    """An admitted provider could not be read safely."""


class ProviderRuntimePolicy(BaseModel):
    """Exact, code-reviewed transport contract for one provider adapter."""

    model_config = ConfigDict(frozen=True)

    contract: str = CONTEXT_PROVIDER_RUNTIME_CONTRACT
    provider_id: str = Field(min_length=1, max_length=180)
    adapter_id: str = Field(min_length=1, max_length=180)
    adapter_version: str = Field(min_length=1, max_length=80)
    allowed_path_prefixes: tuple[str, ...] = Field(min_length=1)
    allowed_media_types: tuple[str, ...] = Field(min_length=1)
    max_response_bytes: int = Field(gt=0, le=MAX_RUNTIME_RESPONSE_BYTES)
    timeout_seconds: float = Field(gt=0, le=MAX_RUNTIME_TIMEOUT_SECONDS)
    secret_header_name: str | None = Field(default=None, min_length=1, max_length=120)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exact_policy(self) -> "ProviderRuntimePolicy":
        normalized_prefixes: list[str] = []
        for prefix in self.allowed_path_prefixes:
            normalized = prefix.strip()
            decoded = unquote(normalized)
            if (
                not normalized.startswith("/")
                or "?" in normalized
                or "#" in normalized
                or "\\" in normalized
                or any(part == ".." for part in decoded.split("/"))
            ):
                raise ValueError("provider_runtime_invalid_path_prefix")
            normalized_prefixes.append(normalized)
        if len(set(normalized_prefixes)) != len(normalized_prefixes):
            raise ValueError("provider_runtime_duplicate_path_prefix")

        normalized_media_types: list[str] = []
        for media_type in self.allowed_media_types:
            normalized = media_type.casefold().strip()
            if (
                not normalized
                or "/" not in normalized
                or "*" in normalized
                or ";" in normalized
                or any(char.isspace() for char in normalized)
            ):
                raise ValueError("provider_runtime_exact_media_type_required")
            normalized_media_types.append(normalized)
        if len(set(normalized_media_types)) != len(normalized_media_types):
            raise ValueError("provider_runtime_duplicate_media_type")

        if self.secret_header_name is not None:
            header = self.secret_header_name.strip()
            if (
                not header
                or ":" in header
                or "\r" in header
                or "\n" in header
                or header.casefold() in {"host", "content-length"}
            ):
                raise ValueError("provider_runtime_invalid_secret_header")
        return self


class ProviderEvidenceReceipt(BaseModel):
    """Verified external payload plus provenance; never a company-world claim."""

    model_config = ConfigDict(frozen=True)

    contract: str = CONTEXT_PROVIDER_RUNTIME_CONTRACT
    provider_id: str
    adapter_id: str
    adapter_version: str
    purpose: RequestPurpose
    source_url: str
    fetched_at: datetime
    status_code: int
    media_type: str
    byte_size: int
    body_sha256: str
    evidence_fingerprint: str
    adapter_evidence_refs: tuple[str, ...]
    provider_evidence_refs: tuple[str, ...]
    raw_body: bytes


# Production policies are intentionally code-reviewed rather than caller supplied.
# No current provider is promoted here until its exact endpoint/schema and access
# authority are verified. Adapter availability must never silently imply live use.
RUNTIME_POLICIES: dict[str, ProviderRuntimePolicy] = {}


def _normalized_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ProviderRuntimeBlocked("provider_runtime_https_required")
    if parsed.username or parsed.password:
        raise ProviderRuntimeBlocked("provider_runtime_userinfo_forbidden")
    if parsed.fragment:
        raise ProviderRuntimeBlocked("provider_runtime_fragment_forbidden")
    if parsed.port not in (None, 443):
        raise ProviderRuntimeBlocked("provider_runtime_nonstandard_port_forbidden")
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        raise ProviderRuntimeBlocked("provider_runtime_host_required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ProviderRuntimeBlocked("provider_runtime_ip_literal_forbidden")


def _path_is_allowed(url: str, policy: ProviderRuntimePolicy) -> bool:
    path = unquote(urlparse(url).path or "/")
    if "\\" in path or any(part == ".." for part in path.split("/")):
        return False
    for prefix in policy.allowed_path_prefixes:
        normalized = prefix.rstrip("/") or "/"
        if normalized == "/" or path == normalized or path.startswith(f"{normalized}/"):
            return True
    return False


def _validate_runtime_authority(
    plan: ProviderRequestPlan,
) -> tuple[ContextProviderSpec, ProviderRuntimePolicy]:
    if plan.contract != CONTEXT_PROVIDER_GATEWAY_CONTRACT:
        raise ProviderRuntimeBlocked("provider_runtime_gateway_contract_mismatch")
    if plan.method.upper() != "GET":
        raise ProviderRuntimeBlocked("provider_runtime_read_only_get_required")
    if not plan.execution_permitted or plan.blockers:
        raise ProviderRuntimeBlocked("provider_runtime_request_plan_not_executable")

    provider = require_provider(plan.provider_id)
    if not provider.production_enabled:
        raise ProviderRuntimeBlocked("provider_runtime_provider_not_production_enabled")
    if not provider.exact_adapter_verified:
        raise ProviderRuntimeBlocked("provider_runtime_adapter_not_registry_verified")

    policy = RUNTIME_POLICIES.get(plan.provider_id)
    if policy is None:
        raise ProviderRuntimeBlocked("provider_runtime_exact_policy_missing")
    if policy.provider_id != plan.provider_id:
        raise ProviderRuntimeBlocked("provider_runtime_policy_provider_mismatch")

    host = _normalized_host(plan.url)
    allowed_hosts = {item.casefold().rstrip(".") for item in provider.allowed_hosts}
    if host not in allowed_hosts:
        raise ProviderRuntimeBlocked("provider_runtime_host_not_allowlisted")
    if not _path_is_allowed(plan.url, policy):
        raise ProviderRuntimeBlocked("provider_runtime_path_not_allowlisted")
    for key, _ in parse_qsl(urlparse(plan.url).query, keep_blank_values=True):
        if key.casefold() in SENSITIVE_QUERY_KEYS:
            raise ProviderRuntimeBlocked("provider_runtime_secret_in_query_forbidden")
    return provider, policy


def _request_headers(
    *,
    provider: ContextProviderSpec,
    policy: ProviderRuntimePolicy,
    plan: ProviderRequestPlan,
    secret_value: str | None,
) -> dict[str, str]:
    headers = {
        "Accept": ", ".join(policy.allowed_media_types),
        "User-Agent": "EAY-Jarvis-Context/1.0",
    }
    if provider.requires_secret:
        if not plan.secret_ref or not secret_value:
            raise ProviderRuntimeBlocked("provider_runtime_secret_material_missing")
        if policy.secret_header_name is None:
            raise ProviderRuntimeBlocked("provider_runtime_secret_header_contract_missing")
        headers[policy.secret_header_name] = secret_value
    elif secret_value is not None:
        raise ProviderRuntimeBlocked("provider_runtime_unexpected_secret_material")
    return headers


def _validate_response_headers(
    response: httpx.Response,
    *,
    policy: ProviderRuntimePolicy,
) -> str:
    if 300 <= response.status_code < 400:
        raise ProviderRuntimeBlocked("provider_runtime_redirect_forbidden")
    if not 200 <= response.status_code < 300:
        raise ProviderRuntimeUnavailable("provider_runtime_upstream_non_success")

    media_type = response.headers.get("content-type", "").split(";", 1)[0].casefold().strip()
    allowed_media_types = {item.casefold().strip() for item in policy.allowed_media_types}
    if not media_type:
        raise ProviderRuntimeBlocked("provider_runtime_content_type_required")
    if media_type not in allowed_media_types:
        raise ProviderRuntimeBlocked("provider_runtime_content_type_not_allowlisted")

    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise ProviderRuntimeBlocked("provider_runtime_invalid_content_length") from exc
        if declared_size < 0 or declared_size > policy.max_response_bytes:
            raise ProviderRuntimeBlocked("provider_runtime_declared_response_too_large")
    return media_type


def _read_bounded_body(response: httpx.Response, *, max_bytes: int) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ProviderRuntimeBlocked("provider_runtime_response_too_large")
    return bytes(body)


def execute_provider_request(
    plan: ProviderRequestPlan,
    *,
    secret_value: str | None = None,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
) -> ProviderEvidenceReceipt:
    """Execute one approved read without redirects, fallback, or causal promotion."""

    provider, policy = _validate_runtime_authority(plan)
    headers = _request_headers(
        provider=provider,
        policy=policy,
        plan=plan,
        secret_value=secret_value,
    )

    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=policy.timeout_seconds,
            transport=transport,
            trust_env=False,
        ) as client:
            with client.stream("GET", plan.url, headers=headers) as response:
                media_type = _validate_response_headers(response, policy=policy)
                raw_body = _read_bounded_body(response, max_bytes=policy.max_response_bytes)
                status_code = response.status_code
    except (ProviderRuntimeBlocked, ProviderRuntimeUnavailable):
        raise
    except httpx.HTTPError as exc:
        raise ProviderRuntimeUnavailable("provider_runtime_transport_failure") from exc

    fetched_at = now or datetime.now(UTC)
    if fetched_at.tzinfo is None:
        raise ValueError("provider_runtime_fetched_at_timezone_required")
    fetched_at = fetched_at.astimezone(UTC)
    body_sha256 = hashlib.sha256(raw_body).hexdigest()
    fingerprint_material = "\n".join(
        (
            CONTEXT_PROVIDER_RUNTIME_CONTRACT,
            plan.provider_id,
            policy.adapter_id,
            policy.adapter_version,
            plan.url,
            media_type,
            body_sha256,
        )
    ).encode("utf-8")
    evidence_fingerprint = hashlib.sha256(fingerprint_material).hexdigest()

    return ProviderEvidenceReceipt(
        provider_id=plan.provider_id,
        adapter_id=policy.adapter_id,
        adapter_version=policy.adapter_version,
        purpose=plan.purpose,
        source_url=plan.url,
        fetched_at=fetched_at,
        status_code=status_code,
        media_type=media_type,
        byte_size=len(raw_body),
        body_sha256=body_sha256,
        evidence_fingerprint=evidence_fingerprint,
        adapter_evidence_refs=policy.evidence_refs,
        provider_evidence_refs=provider.evidence_refs,
        raw_body=raw_body,
    )
