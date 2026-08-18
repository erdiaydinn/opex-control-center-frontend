"""Compose registry identity, authenticated session evidence and browser harnesses.

This is the post-authentication entrypoint for learning a real enterprise web
application.  It turns an identity-bound managed browser session into a
read-only Playwright onboarding runtime, optionally adding agent-browser as a
semantic read secondary.  It never enables writes or direct API execution.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, model_validator

from .agent_browser_runtime import AgentBrowserCorporateSessionConfig
from .browser_harness_router import (
    BrowserHarness,
    BrowserHarnessRequest,
    BrowserHarnessRoute,
    BrowserMissionKind,
    route_browser_harness,
)
from .enterprise_application_registry import (
    EnterpriseApplicationEntry,
    load_enterprise_application_registry,
)
from .playwright_computer_runtime import PlaywrightSessionConfig

ENTERPRISE_BROWSER_ONBOARDING_CONTRACT = "eay-enterprise-browser-onboarding-v1"


class AuthenticatedBrowserSessionEvidence(BaseModel):
    application_id: str = Field(min_length=1)
    tenant_scope_ref: str = Field(min_length=1)
    auth_context_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    observed_at: datetime
    observed_url: str = Field(min_length=8, exclude=True)
    authenticated: bool
    network_egress_boundary_ref: str | None = None

    @model_validator(mode="after")
    def evidence_is_time_bound_and_authenticated(self) -> "AuthenticatedBrowserSessionEvidence":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("enterprise_browser_session_requires_timezone")
        if not self.authenticated:
            raise ValueError("enterprise_browser_onboarding_requires_authenticated_session")
        parsed = urlparse(self.observed_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("enterprise_browser_session_https_url_required")
        if parsed.username or parsed.password:
            raise ValueError("enterprise_browser_session_url_userinfo_forbidden")
        return self


class EnterpriseBrowserOnboardingRuntime(BaseModel):
    contract: str = ENTERPRISE_BROWSER_ONBOARDING_CONTRACT
    application_id: str
    tenant_scope_ref: str
    auth_context_ref: str
    identity_evidence_ref: str
    observed_origin_shape: str
    harness_route: BrowserHarnessRoute
    playwright: PlaywrightSessionConfig
    agent_browser: AgentBrowserCorporateSessionConfig | None = None
    read_only: bool = True
    write_execution_allowed: bool = False
    direct_api_execution_allowed: bool = False
    application_field_production_verified: bool = False
    raw_observed_url_retained: bool = False

    @model_validator(mode="after")
    def onboarding_runtime_never_promotes_write_or_raw_url(self) -> "EnterpriseBrowserOnboardingRuntime":
        if not self.read_only:
            raise ValueError("enterprise_browser_onboarding_must_be_read_only")
        if self.write_execution_allowed or self.direct_api_execution_allowed:
            raise ValueError("enterprise_browser_onboarding_never_enables_execution")
        if self.application_field_production_verified:
            raise ValueError("enterprise_browser_onboarding_session_is_not_field_acceptance")
        if self.raw_observed_url_retained:
            raise ValueError("enterprise_browser_onboarding_cannot_retain_raw_observed_url")
        if self.harness_route.primary is not BrowserHarness.PLAYWRIGHT:
            raise ValueError("enterprise_read_onboarding_requires_playwright_primary")
        return self


def _origin_shape(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    return urlunparse(("https", host, parsed.path or "/", "", "", ""))


def _validate_session_against_application(
    *,
    application: EnterpriseApplicationEntry,
    session: AuthenticatedBrowserSessionEvidence,
) -> None:
    if session.application_id != application.application_id:
        raise ValueError("enterprise_browser_session_application_mismatch")
    host = (urlparse(session.observed_url).hostname or "").casefold().rstrip(".")
    if host not in set(application.allowed_primary_hosts):
        raise ValueError("enterprise_browser_session_host_not_registered")
    if not application.read_onboarding_enabled:
        raise ValueError("enterprise_application_read_onboarding_disabled")


def prepare_enterprise_read_onboarding_runtime(
    *,
    application_id: str,
    session: AuthenticatedBrowserSessionEvidence,
    cdp_endpoint: str = "http://127.0.0.1:9222",
    agent_browser_available: bool = False,
    agent_browser_session_name: str = "eay-enterprise-read",
) -> EnterpriseBrowserOnboardingRuntime:
    registry = load_enterprise_application_registry()
    application = registry.by_id().get(application_id)
    if application is None:
        raise ValueError("enterprise_application_not_registered")
    _validate_session_against_application(application=application, session=session)

    playwright = PlaywrightSessionConfig(
        application_id=application.application_id,
        tenant_scope_ref=session.tenant_scope_ref,
        auth_context_ref=session.auth_context_ref,
        allowed_hosts=frozenset(application.allowed_primary_hosts),
        cdp_endpoint=cdp_endpoint,
    )
    route = route_browser_harness(
        BrowserHarnessRequest(
            application_id=application.application_id,
            tenant_scope_ref=session.tenant_scope_ref,
            mission_kind=BrowserMissionKind.READ_ONBOARDING,
            existing_managed_session=True,
            live_session_identity_bound=True,
            playwright_available=True,
            agent_browser_available=agent_browser_available,
            agent_browser_pin_tab=agent_browser_available,
            network_egress_boundary_ref=session.network_egress_boundary_ref,
        )
    )

    agent_browser = None
    if BrowserHarness.AGENT_BROWSER in route.secondary:
        if not session.network_egress_boundary_ref:
            raise ValueError("agent_browser_secondary_requires_egress_boundary_ref")
        agent_browser = AgentBrowserCorporateSessionConfig(
            application_id=application.application_id,
            tenant_scope_ref=session.tenant_scope_ref,
            auth_context_ref=session.auth_context_ref,
            network_egress_boundary_ref=session.network_egress_boundary_ref,
            allowed_hosts=frozenset(application.allowed_primary_hosts),
            session_name=agent_browser_session_name,
            cdp_endpoint=cdp_endpoint,
        )

    return EnterpriseBrowserOnboardingRuntime(
        application_id=application.application_id,
        tenant_scope_ref=session.tenant_scope_ref,
        auth_context_ref=session.auth_context_ref,
        identity_evidence_ref=session.identity_evidence_ref,
        observed_origin_shape=_origin_shape(session.observed_url),
        harness_route=route,
        playwright=playwright,
        agent_browser=agent_browser,
    )
