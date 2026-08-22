"""Fail-closed request planning for approved Jarvis context providers.

This module deliberately does not perform network I/O. It validates the target
against the provider registry and returns an auditable request plan. Runtime
adapters may later execute only plans that pass their own adapter verification,
credential, rate-limit and production-activation gates.
"""

from __future__ import annotations

import ipaddress
from enum import Enum
from urllib.parse import parse_qsl, urlparse

from pydantic import BaseModel, Field, model_validator

from .context_provider_registry import ProviderAccessMode, require_provider

CONTEXT_PROVIDER_GATEWAY_CONTRACT = "eay-context-provider-gateway-v1"
SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "key",
    "token",
    "access_token",
    "secret",
    "password",
    "passwd",
}


class RequestPurpose(str, Enum):
    ONE_SHOT_OBSERVATION = "one_shot_observation"
    CONTINUOUS_INGESTION = "continuous_ingestion"


class ProviderRequestPlan(BaseModel):
    contract: str = CONTEXT_PROVIDER_GATEWAY_CONTRACT
    provider_id: str
    method: str = "GET"
    url: str
    purpose: RequestPurpose
    secret_ref: str | None = None
    authorization_evidence_ref: str | None = None
    execution_permitted: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def prohibit_unverified_execution(self) -> "ProviderRequestPlan":
        if self.execution_permitted and self.blockers:
            raise ValueError("provider_request_execution_cannot_ignore_blockers")
        return self


def _validate_target(provider_id: str, url: str) -> None:
    provider = require_provider(provider_id)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("provider_request_https_required")
    if parsed.username or parsed.password:
        raise ValueError("provider_request_userinfo_forbidden")
    if parsed.fragment:
        raise ValueError("provider_request_fragment_forbidden")
    if parsed.port not in (None, 443):
        raise ValueError("provider_request_nonstandard_port_forbidden")
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        raise ValueError("provider_request_host_required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("provider_request_ip_literal_forbidden")
    allowed = {item.casefold().rstrip(".") for item in provider.allowed_hosts}
    if host not in allowed:
        raise ValueError("provider_request_host_not_allowlisted")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if key.casefold() in SENSITIVE_QUERY_KEYS:
            raise ValueError("provider_request_secret_in_query_forbidden")


def plan_provider_request(
    *,
    provider_id: str,
    url: str,
    purpose: RequestPurpose,
    secret_ref: str | None = None,
    authorization_evidence_ref: str | None = None,
) -> ProviderRequestPlan:
    provider = require_provider(provider_id)
    _validate_target(provider_id, url)

    blockers: list[str] = []
    if provider.requires_secret and not secret_ref:
        blockers.append("provider_secret_reference_missing")
    if provider.access_mode is ProviderAccessMode.AUTHORIZATION_REQUIRED and not authorization_evidence_ref:
        blockers.append("provider_authorization_evidence_missing")
    if purpose is RequestPurpose.CONTINUOUS_INGESTION and not provider.continuous_ingestion_authorized:
        blockers.append("provider_continuous_ingestion_not_authorized")
    if not provider.exact_adapter_verified:
        blockers.append("provider_exact_adapter_not_verified")
    if not provider.production_enabled:
        blockers.append("provider_production_not_enabled")

    return ProviderRequestPlan(
        provider_id=provider_id,
        url=url,
        purpose=purpose,
        secret_ref=secret_ref,
        authorization_evidence_ref=authorization_evidence_ref,
        execution_permitted=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
    )
