"""Fail-closed routing between EAY browser harnesses.

Playwright remains the authoritative execution/network-observation harness.
agent-browser is an optional semantic-read accelerator for pinned, identity-
bound corporate tabs.  This router prevents a future caller from accidentally
using the semantic exploration harness for production mutations.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

BROWSER_HARNESS_ROUTER_CONTRACT = "eay-browser-harness-router-v1"


class BrowserHarness(str, Enum):
    PLAYWRIGHT = "playwright"
    AGENT_BROWSER = "agent_browser"


class BrowserMissionKind(str, Enum):
    SEMANTIC_READ = "semantic_read"
    READ_ONBOARDING = "read_onboarding"
    NETWORK_API_DISCOVERY = "network_api_discovery"
    AUTHORITATIVE_STATE_VERIFICATION = "authoritative_state_verification"
    WRITE_EXECUTION = "write_execution"


class BrowserHarnessRequest(BaseModel):
    application_id: str = Field(min_length=1)
    tenant_scope_ref: str = Field(min_length=1)
    mission_kind: BrowserMissionKind
    existing_managed_session: bool
    live_session_identity_bound: bool
    playwright_available: bool = True
    agent_browser_available: bool = False
    agent_browser_pin_tab: bool = False
    network_egress_boundary_ref: str | None = None
    mutation_capability_qualified: bool = False
    effect_verifier_ref: str | None = None


class BrowserHarnessRoute(BaseModel):
    contract: str = BROWSER_HARNESS_ROUTER_CONTRACT
    application_id: str
    tenant_scope_ref: str
    mission_kind: BrowserMissionKind
    primary: BrowserHarness | None = None
    secondary: tuple[BrowserHarness, ...] = ()
    allowed: bool
    mutation_allowed: bool = False
    network_observation_required: bool = False
    authoritative_effect_verification_required: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def route_cannot_mix_blocked_or_unsafe_execution(self) -> "BrowserHarnessRoute":
        if self.allowed:
            if self.primary is None or self.blockers:
                raise ValueError("allowed_browser_harness_route_requires_primary_without_blockers")
        elif not self.blockers:
            raise ValueError("blocked_browser_harness_route_requires_blocker")
        if self.mutation_allowed and self.primary is not BrowserHarness.PLAYWRIGHT:
            raise ValueError("browser_mutation_requires_playwright_primary")
        if self.mission_kind is BrowserMissionKind.WRITE_EXECUTION:
            if BrowserHarness.AGENT_BROWSER in self.secondary:
                raise ValueError("agent_browser_forbidden_in_write_route")
            if not self.authoritative_effect_verification_required:
                raise ValueError("browser_write_requires_authoritative_effect_verification")
        return self


def _agent_browser_safe_for_corporate_read(request: BrowserHarnessRequest) -> bool:
    return bool(
        request.agent_browser_available
        and request.existing_managed_session
        and request.live_session_identity_bound
        and request.agent_browser_pin_tab
        and request.network_egress_boundary_ref
    )


def route_browser_harness(request: BrowserHarnessRequest) -> BrowserHarnessRoute:
    blockers: list[str] = []

    if request.mission_kind is BrowserMissionKind.WRITE_EXECUTION:
        if not request.playwright_available:
            blockers.append("browser_write_playwright_unavailable")
        if not request.existing_managed_session:
            blockers.append("browser_write_managed_session_missing")
        if not request.live_session_identity_bound:
            blockers.append("browser_write_session_identity_unverified")
        if not request.mutation_capability_qualified:
            blockers.append("browser_write_capability_not_qualified")
        if not request.effect_verifier_ref:
            blockers.append("browser_write_effect_verifier_missing")
        if blockers:
            return BrowserHarnessRoute(
                application_id=request.application_id,
                tenant_scope_ref=request.tenant_scope_ref,
                mission_kind=request.mission_kind,
                allowed=False,
                authoritative_effect_verification_required=True,
                blockers=tuple(blockers),
            )
        return BrowserHarnessRoute(
            application_id=request.application_id,
            tenant_scope_ref=request.tenant_scope_ref,
            mission_kind=request.mission_kind,
            primary=BrowserHarness.PLAYWRIGHT,
            allowed=True,
            mutation_allowed=True,
            authoritative_effect_verification_required=True,
        )

    if request.mission_kind is BrowserMissionKind.NETWORK_API_DISCOVERY:
        if not request.playwright_available:
            return BrowserHarnessRoute(
                application_id=request.application_id,
                tenant_scope_ref=request.tenant_scope_ref,
                mission_kind=request.mission_kind,
                allowed=False,
                network_observation_required=True,
                blockers=("browser_network_discovery_requires_playwright",),
            )
        return BrowserHarnessRoute(
            application_id=request.application_id,
            tenant_scope_ref=request.tenant_scope_ref,
            mission_kind=request.mission_kind,
            primary=BrowserHarness.PLAYWRIGHT,
            allowed=True,
            network_observation_required=True,
        )

    agent_browser_safe = _agent_browser_safe_for_corporate_read(request)

    if request.mission_kind is BrowserMissionKind.READ_ONBOARDING:
        if not request.playwright_available:
            return BrowserHarnessRoute(
                application_id=request.application_id,
                tenant_scope_ref=request.tenant_scope_ref,
                mission_kind=request.mission_kind,
                allowed=False,
                network_observation_required=True,
                blockers=("browser_read_onboarding_requires_playwright_network_observation",),
            )
        return BrowserHarnessRoute(
            application_id=request.application_id,
            tenant_scope_ref=request.tenant_scope_ref,
            mission_kind=request.mission_kind,
            primary=BrowserHarness.PLAYWRIGHT,
            secondary=((BrowserHarness.AGENT_BROWSER,) if agent_browser_safe else ()),
            allowed=True,
            network_observation_required=True,
        )

    if request.mission_kind is BrowserMissionKind.AUTHORITATIVE_STATE_VERIFICATION:
        if not request.playwright_available:
            return BrowserHarnessRoute(
                application_id=request.application_id,
                tenant_scope_ref=request.tenant_scope_ref,
                mission_kind=request.mission_kind,
                allowed=False,
                authoritative_effect_verification_required=True,
                blockers=("authoritative_state_verification_requires_playwright",),
            )
        return BrowserHarnessRoute(
            application_id=request.application_id,
            tenant_scope_ref=request.tenant_scope_ref,
            mission_kind=request.mission_kind,
            primary=BrowserHarness.PLAYWRIGHT,
            secondary=((BrowserHarness.AGENT_BROWSER,) if agent_browser_safe else ()),
            allowed=True,
            authoritative_effect_verification_required=True,
        )

    if request.mission_kind is BrowserMissionKind.SEMANTIC_READ:
        if agent_browser_safe:
            return BrowserHarnessRoute(
                application_id=request.application_id,
                tenant_scope_ref=request.tenant_scope_ref,
                mission_kind=request.mission_kind,
                primary=BrowserHarness.AGENT_BROWSER,
                secondary=((BrowserHarness.PLAYWRIGHT,) if request.playwright_available else ()),
                allowed=True,
            )
        if request.playwright_available:
            return BrowserHarnessRoute(
                application_id=request.application_id,
                tenant_scope_ref=request.tenant_scope_ref,
                mission_kind=request.mission_kind,
                primary=BrowserHarness.PLAYWRIGHT,
                allowed=True,
            )
        return BrowserHarnessRoute(
            application_id=request.application_id,
            tenant_scope_ref=request.tenant_scope_ref,
            mission_kind=request.mission_kind,
            allowed=False,
            blockers=("no_safe_browser_harness_available",),
        )

    raise ValueError("browser_mission_kind_unsupported")
