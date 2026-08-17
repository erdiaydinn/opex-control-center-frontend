"""Governed API auto-discovery from traffic the authorized UI actually emits.

Jarvis must not require a user to hand over undocumented API docs. Instead it
may observe an already-authorized browser/application session, correlate HTTP
exchanges with the user's UI action, and derive endpoint candidates. This
module performs *discovery only*: no active scanning, path guessing, credential
harvesting, request replay, or network I/O is allowed here.

The security boundary is intentional:
- only explicitly allowlisted application hosts are considered;
- only traffic that was actually observed is eligible;
- raw Authorization/Cookie values are never represented by this contract;
- secret-bearing query parameters are removed before the URL is retained;
- static assets are ignored;
- mutating candidates require a correlated user action before promotion;
- discovered endpoints are evidence, not production capabilities.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections import defaultdict
from enum import Enum
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator, model_validator

API_DISCOVERY_CONTRACT = "eay-api-auto-discovery-v1"

_UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_INTEGER_SEGMENT = re.compile(r"^[0-9]{1,18}$")
_LONG_HEX_SEGMENT = re.compile(r"^[0-9a-fA-F]{16,64}$")
_STATIC_SUFFIXES = (
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp4",
    ".webm",
)
_STATIC_RESOURCE_TYPES = {"image", "stylesheet", "font", "media"}
_SECRETISH_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "jwt",
    "key",
    "password",
    "passwd",
    "secret",
    "token",
}


class CaptureSource(str, Enum):
    PLAYWRIGHT_NETWORK = "playwright_network"
    CHROME_DEVTOOLS = "chrome_devtools"
    HAR = "har"
    MITMPROXY = "mitmproxy"
    KEPLOY = "keploy"
    OPENAPI_DOCUMENT = "openapi_document"


class OperationKind(str, Enum):
    READ = "read"
    WRITE = "write"
    UNKNOWN = "unknown"


def _sanitize_url(url: str) -> str:
    """Remove secret-bearing query pairs before an observed URL is retained."""
    parsed = urlparse(url)
    safe_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _SECRETISH_QUERY_KEYS
    ]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(safe_query, doseq=True),
            "",
        )
    )


class ObservedHttpExchange(BaseModel):
    """A secret-free fingerprint of one exchange observed in an authorized session."""

    contract: str = API_DISCOVERY_CONTRACT
    application_id: str = Field(min_length=1)
    capture_source: CaptureSource
    method: str = Field(min_length=3, max_length=12)
    url: str = Field(min_length=8)
    status_code: int = Field(ge=100, le=599)
    resource_type: str | None = None
    request_content_type: str | None = None
    response_content_type: str | None = None
    request_body_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    response_body_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    user_action_ref: str | None = None
    auth_context_ref: str | None = None
    tenant_scope_ref: str | None = None
    authorization_header_present: bool = False
    cookie_header_present: bool = False
    observed: bool = True

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def observed_exchange_is_fail_closed(self) -> "ObservedHttpExchange":
        if not self.observed:
            raise ValueError("api_discovery_requires_observed_traffic")
        parsed = urlparse(self.url)
        if parsed.scheme != "https":
            raise ValueError("api_discovery_https_required")
        if parsed.username or parsed.password:
            raise ValueError("api_discovery_url_userinfo_forbidden")
        if parsed.fragment:
            raise ValueError("api_discovery_url_fragment_forbidden")
        host = (parsed.hostname or "").strip().casefold().rstrip(".")
        if not host:
            raise ValueError("api_discovery_host_required")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("api_discovery_ip_literal_forbidden")
        self.url = _sanitize_url(self.url)
        return self

    @property
    def host(self) -> str:
        return (urlparse(self.url).hostname or "").casefold().rstrip(".")

    @property
    def path(self) -> str:
        return urlparse(self.url).path or "/"

    def query_parameter_names(self) -> tuple[str, ...]:
        names = {key for key, _ in parse_qsl(urlparse(self.url).query, keep_blank_values=True)}
        return tuple(sorted(names))


class EndpointCandidate(BaseModel):
    contract: str = API_DISCOVERY_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    application_id: str
    host: str
    method: str
    path_template: str
    query_parameters: tuple[str, ...] = ()
    operation_kind: OperationKind
    observation_count: int = Field(ge=1)
    successful_observation_count: int = Field(ge=0)
    status_codes: tuple[int, ...]
    capture_sources: tuple[CaptureSource, ...]
    user_action_refs: tuple[str, ...] = ()
    auth_context_refs: tuple[str, ...] = ()
    tenant_scope_refs: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    eligible_for_promotion: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def promotion_cannot_ignore_blockers(self) -> "EndpointCandidate":
        if self.eligible_for_promotion and self.blockers:
            raise ValueError("api_candidate_promotion_cannot_ignore_blockers")
        return self


def _operation_kind(method: str) -> OperationKind:
    if method in {"GET", "HEAD", "OPTIONS"}:
        return OperationKind.READ
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return OperationKind.WRITE
    return OperationKind.UNKNOWN


def _path_template(path: str) -> str:
    parts: list[str] = []
    for raw in path.split("/"):
        if not raw:
            continue
        if _UUID_SEGMENT.fullmatch(raw):
            parts.append("{uuid}")
        elif _INTEGER_SEGMENT.fullmatch(raw):
            parts.append("{int}")
        elif _LONG_HEX_SEGMENT.fullmatch(raw):
            parts.append("{hex_id}")
        else:
            parts.append(raw)
    return "/" + "/".join(parts)


def _is_probable_api_exchange(exchange: ObservedHttpExchange) -> bool:
    if exchange.resource_type and exchange.resource_type.casefold() in _STATIC_RESOURCE_TYPES:
        return False
    if exchange.path.casefold().endswith(_STATIC_SUFFIXES):
        return False
    response_type = (exchange.response_content_type or "").casefold()
    request_type = (exchange.request_content_type or "").casefold()
    if "json" in response_type or "json" in request_type or "graphql" in request_type:
        return True
    if exchange.resource_type and exchange.resource_type.casefold() in {"xhr", "fetch"}:
        return True
    return exchange.method not in {"GET", "HEAD"}


def _candidate_fingerprint(
    *, application_id: str, host: str, method: str, path_template: str, query_parameters: tuple[str, ...]
) -> str:
    canonical = json.dumps(
        {
            "application_id": application_id,
            "host": host,
            "method": method,
            "path_template": path_template,
            "query_parameters": query_parameters,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def discover_api_candidates(
    exchanges: list[ObservedHttpExchange],
    *,
    allowed_hosts: set[str],
) -> list[EndpointCandidate]:
    """Derive candidates only from allowlisted, actually-observed application traffic."""

    normalized_allowed = {host.casefold().rstrip(".") for host in allowed_hosts}
    grouped: dict[tuple[str, str, str, str, tuple[str, ...]], list[ObservedHttpExchange]] = defaultdict(list)

    for exchange in exchanges:
        if exchange.host not in normalized_allowed:
            continue
        if not _is_probable_api_exchange(exchange):
            continue
        template = _path_template(exchange.path)
        query_parameters = exchange.query_parameter_names()
        grouped[(exchange.application_id, exchange.host, exchange.method, template, query_parameters)].append(exchange)

    candidates: list[EndpointCandidate] = []
    for (application_id, host, method, template, query_parameters), observations in grouped.items():
        operation_kind = _operation_kind(method)
        successful = sum(1 for item in observations if 200 <= item.status_code < 400)
        actions = tuple(sorted({item.user_action_ref for item in observations if item.user_action_ref}))
        auth_refs = tuple(sorted({item.auth_context_ref for item in observations if item.auth_context_ref}))
        tenant_refs = tuple(sorted({item.tenant_scope_ref for item in observations if item.tenant_scope_ref}))
        sources = tuple(sorted({item.capture_source for item in observations}, key=lambda item: item.value))
        statuses = tuple(sorted({item.status_code for item in observations}))

        blockers: list[str] = []
        if successful == 0:
            blockers.append("api_candidate_no_successful_observation")
        if operation_kind is OperationKind.UNKNOWN:
            blockers.append("api_candidate_operation_kind_unknown")
        if operation_kind is OperationKind.WRITE and not actions:
            blockers.append("api_candidate_write_not_correlated_to_user_action")
        if any(item.authorization_header_present or item.cookie_header_present for item in observations) and not auth_refs:
            blockers.append("api_candidate_auth_context_not_bound")
        if not tenant_refs:
            blockers.append("api_candidate_tenant_scope_not_bound")

        confidence = 0.35
        if successful:
            confidence += 0.20
        if len(observations) >= 2:
            confidence += 0.15
        if actions:
            confidence += 0.10
        if len(sources) >= 2:
            confidence += 0.10
        if auth_refs and tenant_refs:
            confidence += 0.10
        confidence = min(confidence, 0.95)

        candidates.append(
            EndpointCandidate(
                candidate_id=_candidate_fingerprint(
                    application_id=application_id,
                    host=host,
                    method=method,
                    path_template=template,
                    query_parameters=query_parameters,
                ),
                application_id=application_id,
                host=host,
                method=method,
                path_template=template,
                query_parameters=query_parameters,
                operation_kind=operation_kind,
                observation_count=len(observations),
                successful_observation_count=successful,
                status_codes=statuses,
                capture_sources=sources,
                user_action_refs=actions,
                auth_context_refs=auth_refs,
                tenant_scope_refs=tenant_refs,
                confidence=confidence,
                eligible_for_promotion=not blockers,
                blockers=tuple(dict.fromkeys(blockers)),
            )
        )

    return sorted(candidates, key=lambda item: (-item.confidence, item.host, item.path_template, item.method))