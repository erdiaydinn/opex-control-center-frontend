"""Governed registry of enterprise applications Jarvis may observe or operate.

The registry separates *identity known* from *live production verified*.  A URL
supplied by a user can be registered so Jarvis stops inventing synthetic hosts,
but that does not prove authentication behavior, DOM/API semantics, tenant
scope, or write safety.  Production write/direct-API flags remain fail-closed
until separate live onboarding and effect-verification evidence exists.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

ENTERPRISE_APPLICATION_REGISTRY_CONTRACT = "eay-enterprise-application-registry-v1"
DEFAULT_APPLICATION_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "enterprise_application_registry.json"
)


class ApplicationEnvironment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ApplicationIdentitySource(str, Enum):
    USER_SUPPLIED = "user_supplied"
    LIVE_OBSERVED = "live_observed"
    OFFICIAL_DOCUMENTATION = "official_documentation"


class AuthenticationProvider(str, Enum):
    UNKNOWN = "unknown"
    OKTA_USER_REPORTED = "okta_user_reported"
    OKTA_LIVE_OBSERVED = "okta_live_observed"


class EnterpriseApplicationEntry(BaseModel):
    application_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    environment: ApplicationEnvironment
    canonical_entry_url: str = Field(min_length=8)
    allowed_primary_hosts: tuple[str, ...] = Field(min_length=1)
    identity_source: ApplicationIdentitySource
    authentication_provider: AuthenticationProvider = AuthenticationProvider.UNKNOWN
    reported_authentication_factors: tuple[str, ...] = ()
    managed_existing_browser_preferred: bool = True
    read_onboarding_enabled: bool = True
    write_execution_enabled: bool = False
    direct_api_execution_enabled: bool = False
    live_session_verified: bool = False
    authoritative_readback_verified: bool = False
    field_production_verified: bool = False
    secrets_retained: bool = False
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def application_identity_is_fail_closed(self) -> "EnterpriseApplicationEntry":
        parsed = urlparse(self.canonical_entry_url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme != "https" or not host:
            raise ValueError("enterprise_application_https_entry_url_required")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("enterprise_application_entry_url_must_be_secret_free")
        normalized_hosts = tuple(sorted({item.casefold().rstrip(".") for item in self.allowed_primary_hosts}))
        if host not in normalized_hosts:
            raise ValueError("enterprise_application_entry_host_must_be_allowlisted")
        object.__setattr__(self, "allowed_primary_hosts", normalized_hosts)
        if self.secrets_retained:
            raise ValueError("enterprise_application_registry_must_not_retain_secrets")

        if self.identity_source is ApplicationIdentitySource.USER_SUPPLIED:
            if self.live_session_verified or self.authoritative_readback_verified or self.field_production_verified:
                raise ValueError("user_supplied_application_identity_cannot_claim_live_verification")
            if self.authentication_provider is AuthenticationProvider.OKTA_LIVE_OBSERVED:
                raise ValueError("user_supplied_application_identity_cannot_claim_live_okta_observation")

        if self.environment is ApplicationEnvironment.PRODUCTION:
            if self.write_execution_enabled and not (
                self.live_session_verified
                and self.authoritative_readback_verified
                and self.field_production_verified
            ):
                raise ValueError("production_application_write_requires_live_field_proof")
            if self.direct_api_execution_enabled and not (
                self.live_session_verified
                and self.authoritative_readback_verified
                and self.field_production_verified
            ):
                raise ValueError("production_direct_api_requires_live_field_proof")
        return self


class EnterpriseApplicationRegistry(BaseModel):
    contract: str = ENTERPRISE_APPLICATION_REGISTRY_CONTRACT
    version: int = Field(ge=1)
    updated_at: str = Field(min_length=10, max_length=10)
    applications: tuple[EnterpriseApplicationEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def identities_are_unique(self) -> "EnterpriseApplicationRegistry":
        ids = [item.application_id for item in self.applications]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_enterprise_application_id")
        return self

    def by_id(self) -> dict[str, EnterpriseApplicationEntry]:
        return {item.application_id: item for item in self.applications}


def load_enterprise_application_registry_text(source_text: str) -> EnterpriseApplicationRegistry:
    payload = json.loads(source_text)
    return EnterpriseApplicationRegistry.model_validate(payload)


def load_enterprise_application_registry(
    path: str | Path = DEFAULT_APPLICATION_REGISTRY_PATH,
) -> EnterpriseApplicationRegistry:
    return load_enterprise_application_registry_text(Path(path).read_text(encoding="utf-8"))
