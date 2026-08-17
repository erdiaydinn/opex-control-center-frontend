"""Browser-network adapter boundary for Jarvis API learning.

The caller may transiently supply request/response headers and parsed payloads
obtained from Playwright, Chrome DevTools/CDP or a managed HAR capture. This
module immediately reduces them to secret-free structural observations. Raw
header values, cookies, bearer tokens, business values and response bodies are
never retained in the returned model.

No browser is launched and no network request is made here. Runtime browser
integration can later call this pure boundary from an authorized managed
session.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel

from .api_discovery_intelligence import CaptureSource, ObservedHttpExchange
from .api_schema_intelligence import PayloadSchemaObservation, infer_payload_schema

BROWSER_API_OBSERVER_CONTRACT = "eay-browser-api-observer-v1"

_AUTH_HEADER_NAMES = {"authorization", "proxy-authorization"}
_COOKIE_HEADER_NAMES = {"cookie", "set-cookie"}


class BrowserApiObservation(BaseModel):
    contract: str = BROWSER_API_OBSERVER_CONTRACT
    exchange: ObservedHttpExchange
    request_schema: PayloadSchemaObservation | None = None
    response_schema: PayloadSchemaObservation | None = None
    raw_headers_retained: bool = False
    raw_payloads_retained: bool = False


def _normalized_header_names(headers: Mapping[str, Any] | None) -> set[str]:
    if not headers:
        return set()
    return {str(key).strip().casefold() for key in headers}


def observe_browser_exchange(
    *,
    application_id: str,
    capture_source: CaptureSource,
    method: str,
    url: str,
    status_code: int,
    allowed_hosts: set[str],
    resource_type: str | None = None,
    request_headers: Mapping[str, Any] | None = None,
    response_headers: Mapping[str, Any] | None = None,
    request_content_type: str | None = None,
    response_content_type: str | None = None,
    request_payload: Any = None,
    response_payload: Any = None,
    user_action_ref: str | None = None,
    auth_context_ref: str | None = None,
    tenant_scope_ref: str | None = None,
) -> BrowserApiObservation:
    if capture_source not in {
        CaptureSource.PLAYWRIGHT_NETWORK,
        CaptureSource.CHROME_DEVTOOLS,
        CaptureSource.HAR,
    }:
        raise ValueError("browser_api_observer_capture_source_not_browser_managed")

    host = (urlparse(url).hostname or "").casefold().rstrip(".")
    normalized_allowed = {item.casefold().rstrip(".") for item in allowed_hosts}
    if host not in normalized_allowed:
        raise ValueError("browser_api_observer_host_not_allowlisted")

    request_names = _normalized_header_names(request_headers)
    response_names = _normalized_header_names(response_headers)
    request_schema = infer_payload_schema(request_payload) if request_payload is not None else None
    response_schema = infer_payload_schema(response_payload) if response_payload is not None else None

    exchange = ObservedHttpExchange(
        application_id=application_id,
        capture_source=capture_source,
        method=method,
        url=url,
        status_code=status_code,
        resource_type=resource_type,
        request_content_type=request_content_type,
        response_content_type=response_content_type,
        # A structural schema fingerprint is intentionally used rather than an
        # unhashed body digest; deterministic hashes of low-entropy PII values
        # can themselves become disclosure oracles.
        request_body_fingerprint=request_schema.schema_fingerprint if request_schema else None,
        response_body_fingerprint=response_schema.schema_fingerprint if response_schema else None,
        user_action_ref=user_action_ref,
        auth_context_ref=auth_context_ref,
        tenant_scope_ref=tenant_scope_ref,
        authorization_header_present=bool(request_names & _AUTH_HEADER_NAMES),
        cookie_header_present=bool((request_names | response_names) & _COOKIE_HEADER_NAMES),
    )
    return BrowserApiObservation(
        exchange=exchange,
        request_schema=request_schema,
        response_schema=response_schema,
    )
