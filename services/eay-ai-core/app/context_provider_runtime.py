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

CONTEXT_PROVIDER_RUNTIME_CONTRACT = "eay-context-provider-runtime-v2"
MAX_RUNTIME_RESPONSE_BYTES = 5_000_000
MAX_RUNTIME_TIMEOUT_SECONDS = 20.0
_FORBIDDEN_STATIC_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "host", "content-length"}
)


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
    request_headers: tuple[tuple[str, str], ...] = ()
    bootstrap_url: str | None = None
    bootstrap_allowed_media_types: tuple[str, ...] = ()
    bootstrap_max_response_bytes: int = Field(default=100_000, gt=0, le=MAX_RUNTIME_RESPONSE_BYTES)
    bootstrap_headers: tuple[tuple[str, str], ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exact_policy(self) -> ProviderRuntimePolicy:
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

        _validate_media_types(self.allowed_media_types, "provider_runtime")
        _validate_static_headers(self.request_headers, "provider_runtime_request")
        _validate_static_headers(self.bootstrap_headers, "provider_runtime_bootstrap")

        if self.bootstrap_url is None:
            if self.bootstrap_allowed_media_types or self.bootstrap_headers:
                raise ValueError("provider_runtime_bootstrap_contract_incomplete")
        else:
            _validate_url_shape(self.bootstrap_url, "provider_runtime_bootstrap")
            if not self.bootstrap_allowed_media_types:
                raise ValueError("provider_runtime_bootstrap_media_type_required")
            _validate_media_types(
                self.bootstrap_allowed_media_types,
                "provider_runtime_bootstrap",
            )

        if self.secret_header_name is not None:
            header = self.secret_header_name.strip()
            if (
                not header
                or ":" in header
                or "\r" in header
                or "\n" in header
                or header.casefold() in _FORBIDDEN_STATIC_HEADERS
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
    bootstrap_url: str | None = None
    bootstrap_body_sha256: str | None = None
    raw_body: bytes


def _validate_media_types(media_types: tuple[str, ...], prefix: str) -> None:
    normalized_media_types: list[str] = []
    for media_type in media_types:
        normalized = media_type.casefold().strip()
        if (
            not normalized
            or "/" not in normalized
            or "*" in normalized
            or ";" in normalized
            or any(char.isspace() for char in normalized)
        ):
            raise ValueError(f"{prefix}_exact_media_type_required")
        normalized_media_types.append(normalized)
    if len(set(normalized_media_types)) != len(normalized_media_types):
        raise ValueError(f"{prefix}_duplicate_media_type")


def _validate_static_headers(headers: tuple[tuple[str, str], ...], prefix: str) -> None:
    names: list[str] = []
    for name, value in headers:
        normalized_name = name.strip().casefold()
        if (
            not normalized_name
            or ":" in normalized_name
            or normalized_name in _FORBIDDEN_STATIC_HEADERS
            or "\r" in name
            or "\n" in name
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError(f"{prefix}_invalid_static_header")
        names.append(normalized_name)
    if len(set(names)) != len(names):
        raise ValueError(f"{prefix}_duplicate_static_header")


def _validate_url_shape(url: str, prefix: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ProviderRuntimeBlocked(f"{prefix}_https_required")
    if parsed.username or parsed.password:
        raise ProviderRuntimeBlocked(f"{prefix}_userinfo_forbidden")
    if parsed.fragment:
        raise ProviderRuntimeBlocked(f"{prefix}_fragment_forbidden")
    if parsed.port not in (None, 443):
        raise ProviderRuntimeBlocked(f"{prefix}_nonstandard_port_forbidden")
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        raise ProviderRuntimeBlocked(f"{prefix}_host_required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ProviderRuntimeBlocked(f"{prefix}_ip_literal_forbidden")


def _normalized_host(url: str) -> str:
    return _validate_url_shape(url, "provider_runtime")


def _path_is_allowed(url: str, policy: ProviderRuntimePolicy) -> bool:
    path = unquote(urlparse(url).path or "/")
    if "\\" in path or any(part == ".." for part in path.split("/")):
        return False
    for prefix in policy.allowed_path_prefixes:
        normalized = prefix.rstrip("/") or "/"
        if normalized == "/" or path == normalized or path.startswith(f"{normalized}/"):
            return True
    return False


def _query_is_safe(url: str) -> bool:
    return not any(
        key.casefold() in SENSITIVE_QUERY_KEYS
        for key, _ in parse_qsl(urlparse(url).query, keep_blank_values=True)
    )


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
    if not provider.exact_adapter_verified:
        raise ProviderRuntimeBlocked("provider_runtime_adapter_not_registry_verified")
    if plan.purpose is RequestPurpose.ONE_SHOT_OBSERVATION:
        if not provider.one_shot_observation_authorized:
            raise ProviderRuntimeBlocked("provider_runtime_one_shot_not_authorized")
    elif not provider.continuous_ingestion_authorized or not provider.production_enabled:
        raise ProviderRuntimeBlocked("provider_runtime_continuous_not_production_authorized")

    policy = RUNTIME_POLICIES.get(plan.provider_id)
    if policy is None:
        raise ProviderRuntimeBlocked("provider_runtime_exact_policy_missing")
    if policy.provider_id != plan.provider_id:
        raise ProviderRuntimeBlocked("provider_runtime_policy_provider_mismatch")

    allowed_hosts = {item.casefold().rstrip(".") for item in provider.allowed_hosts}
    host = _normalized_host(plan.url)
    if host not in allowed_hosts:
        raise ProviderRuntimeBlocked("provider_runtime_host_not_allowlisted")
    if not _path_is_allowed(plan.url, policy):
        raise ProviderRuntimeBlocked("provider_runtime_path_not_allowlisted")
    if not _query_is_safe(plan.url):
        raise ProviderRuntimeBlocked("provider_runtime_secret_in_query_forbidden")

    if policy.bootstrap_url is not None:
        bootstrap_host = _validate_url_shape(
            policy.bootstrap_url,
            "provider_runtime_bootstrap",
        )
        if bootstrap_host not in allowed_hosts:
            raise ProviderRuntimeBlocked("provider_runtime_bootstrap_host_not_allowlisted")
        if not _query_is_safe(policy.bootstrap_url):
            raise ProviderRuntimeBlocked("provider_runtime_bootstrap_secret_in_query_forbidden")
    return provider, policy


def _headers_with_static(
    *,
    accept: tuple[str, ...],
    static_headers: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    headers = {
        "Accept": ", ".join(accept),
        "User-Agent": "EAY-Jarvis-Context/1.0",
    }
    headers.update(dict(static_headers))
    return headers


def _request_headers(
    *,
    provider: ContextProviderSpec,
    policy: ProviderRuntimePolicy,
    plan: ProviderRequestPlan,
    secret_value: str | None,
) -> dict[str, str]:
    headers = _headers_with_static(
        accept=policy.allowed_media_types,
        static_headers=policy.request_headers,
    )
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
    allowed_media_types: tuple[str, ...],
    max_response_bytes: int,
    prefix: str,
) -> str:
    if 300 <= response.status_code < 400:
        raise ProviderRuntimeBlocked(f"{prefix}_redirect_forbidden")
    if not 200 <= response.status_code < 300:
        raise ProviderRuntimeUnavailable(f"{prefix}_upstream_non_success")

    media_type = response.headers.get("content-type", "").split(";", 1)[0].casefold().strip()
    allowed = {item.casefold().strip() for item in allowed_media_types}
    if not media_type:
        raise ProviderRuntimeBlocked(f"{prefix}_content_type_required")
    if media_type not in allowed:
        raise ProviderRuntimeBlocked(f"{prefix}_content_type_not_allowlisted")

    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise ProviderRuntimeBlocked(f"{prefix}_invalid_content_length") from exc
        if declared_size < 0 or declared_size > max_response_bytes:
            raise ProviderRuntimeBlocked(f"{prefix}_declared_response_too_large")
    return media_type


def _read_bounded_body(response: httpx.Response, *, max_bytes: int, prefix: str) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ProviderRuntimeBlocked(f"{prefix}_response_too_large")
    return bytes(body)


def _bootstrap_session(
    client: httpx.Client,
    *,
    policy: ProviderRuntimePolicy,
) -> tuple[str | None, str | None]:
    if policy.bootstrap_url is None:
        return None, None
    headers = _headers_with_static(
        accept=policy.bootstrap_allowed_media_types,
        static_headers=policy.bootstrap_headers,
    )
    with client.stream("GET", policy.bootstrap_url, headers=headers) as response:
        _validate_response_headers(
            response,
            allowed_media_types=policy.bootstrap_allowed_media_types,
            max_response_bytes=policy.bootstrap_max_response_bytes,
            prefix="provider_runtime_bootstrap",
        )
        raw_body = _read_bounded_body(
            response,
            max_bytes=policy.bootstrap_max_response_bytes,
            prefix="provider_runtime_bootstrap",
        )
    return policy.bootstrap_url, hashlib.sha256(raw_body).hexdigest()


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
            bootstrap_url, bootstrap_body_sha256 = _bootstrap_session(client, policy=policy)
            with client.stream("GET", plan.url, headers=headers) as response:
                media_type = _validate_response_headers(
                    response,
                    allowed_media_types=policy.allowed_media_types,
                    max_response_bytes=policy.max_response_bytes,
                    prefix="provider_runtime",
                )
                raw_body = _read_bounded_body(
                    response,
                    max_bytes=policy.max_response_bytes,
                    prefix="provider_runtime",
                )
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
    fingerprint_material = (
        f"{CONTEXT_PROVIDER_RUNTIME_CONTRACT}\n{plan.provider_id}\n{policy.adapter_id}\n"
        f"{policy.adapter_version}\n{plan.url}\n{media_type}\n{body_sha256}\n"
        f"{bootstrap_url or ''}\n{bootstrap_body_sha256 or ''}"
    ).encode()
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
        bootstrap_url=bootstrap_url,
        bootstrap_body_sha256=bootstrap_body_sha256,
        raw_body=raw_body,
    )


RUNTIME_POLICIES: dict[str, ProviderRuntimePolicy] = {
    "tr-tuik-theme-catalog": ProviderRuntimePolicy(
        provider_id="tr-tuik-theme-catalog",
        adapter_id="tuik-theme-catalog-json",
        adapter_version="1",
        allowed_path_prefixes=("/api/tr/data/statistical-themes",),
        allowed_media_types=("application/json",),
        max_response_bytes=2_000_000,
        timeout_seconds=20.0,
        request_headers=(
            ("Accept-Language", "tr-TR,tr;q=0.9,en;q=0.8"),
            ("Referer", "https://veriportali.tuik.gov.tr/tr/statistical-themes"),
            ("Origin", "https://veriportali.tuik.gov.tr"),
            ("X-Requested-With", "XMLHttpRequest"),
            ("User-Agent", "Mozilla/5.0 EAY-Jarvis-Context/1.0"),
        ),
        bootstrap_url="https://veriportali.tuik.gov.tr/tr/statistical-themes",
        bootstrap_allowed_media_types=("text/html",),
        bootstrap_max_response_bytes=100_000,
        bootstrap_headers=(
            ("Accept-Language", "tr-TR,tr;q=0.9,en;q=0.8"),
            ("User-Agent", "Mozilla/5.0 EAY-Jarvis-Context/1.0"),
        ),
        evidence_refs=(
            "field://tuik/theme-catalog/session-aware-2026-08-21",
            "field://tuik/theme-catalog/schema-2026-08-22",
        ),
    )
}
