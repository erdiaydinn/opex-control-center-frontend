"""Read-only application onboarding for Jarvis computer use.

Jarvis must learn a new enterprise application before it is allowed to mutate
it. This module fingerprints the exact application/environment from managed
browser receipts, rejects mutating traffic, derives read-only API candidates,
and compiles a structured-UI/readback procedure candidate without authorizing
writes. Application, tenant and auth context must remain identical from the
session through browser receipts and captured network observations.

Production/staging/development read verification is never a client-authored
boolean. It must be accompanied by an independent verifier receipt whose
evidence is already present in the onboarding evidence bundle. Synthetic
fixtures may retain the legacy boolean for isolated tests, but are explicitly
labelled synthetic and can never be confused with field evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from .api_discovery_intelligence import EndpointCandidate, OperationKind, discover_api_candidates
from .playwright_computer_runtime import BrowserActionReceipt, LocatorKind
from .playwright_mission_adapter import BrowserEffectVerification, EffectVerificationStatus
from .procedural_memory import (
    ProcedureDemonstration,
    ProceduralCapability,
    ProcedureStep,
    ProcedureStepKind,
    compile_procedure,
    procedure_step_fingerprint,
)

APPLICATION_ONBOARDING_CONTRACT = "eay-application-onboarding-v2"


class ApplicationEnvironmentKind(str, Enum):
    SYNTHETIC = "synthetic"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class OnboardingStatus(str, Enum):
    OBSERVED = "observed"
    READ_CAPABILITY_CANDIDATE = "read_capability_candidate"
    BLOCKED = "blocked"


class TransportPreference(str, Enum):
    OBSERVED_READ_API = "observed_read_api"
    ACCESSIBILITY = "accessibility"
    DOM = "dom"


class ApplicationOnboardingSession(BaseModel):
    session_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    tenant_scope_ref: str = Field(min_length=1)
    auth_context_ref: str = Field(min_length=1)
    environment_kind: ApplicationEnvironmentKind
    allowed_hosts: frozenset[str] = Field(min_length=1)
    observed_at: datetime
    receipts: tuple[BrowserActionReceipt, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    business_write_observed: bool = False
    authoritative_read_verified: bool = False
    authoritative_read_verification: BrowserEffectVerification | None = None
    synthetic_fixture: bool = False

    @model_validator(mode="after")
    def session_is_identity_bound_and_truthful(self) -> "ApplicationOnboardingSession":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("application_onboarding_requires_timezone")
        normalized_hosts = frozenset(item.casefold().rstrip(".") for item in self.allowed_hosts)
        object.__setattr__(self, "allowed_hosts", normalized_hosts)
        if self.environment_kind is ApplicationEnvironmentKind.SYNTHETIC and not self.synthetic_fixture:
            raise ValueError("synthetic_onboarding_environment_requires_fixture_label")
        if self.environment_kind is not ApplicationEnvironmentKind.SYNTHETIC and self.synthetic_fixture:
            raise ValueError("non_synthetic_environment_cannot_claim_synthetic_fixture")

        verification = self.authoritative_read_verification
        if self.environment_kind is not ApplicationEnvironmentKind.SYNTHETIC:
            if self.authoritative_read_verified and verification is None:
                raise ValueError("non_synthetic_read_verification_requires_verifier_receipt")
            if verification is not None:
                if verification.status is not EffectVerificationStatus.VERIFIED_APPLIED:
                    raise ValueError("non_synthetic_read_verifier_must_confirm_authoritative_read")
                if not set(verification.evidence_refs).issubset(set(self.evidence_refs)):
                    raise ValueError("read_verifier_evidence_must_be_bound_to_onboarding_session")
        elif verification is not None and not set(verification.evidence_refs).issubset(set(self.evidence_refs)):
            raise ValueError("read_verifier_evidence_must_be_bound_to_onboarding_session")

        for receipt in self.receipts:
            if receipt.application_id != self.application_id:
                raise ValueError("application_onboarding_receipt_application_mismatch")
            if receipt.tenant_scope_ref != self.tenant_scope_ref:
                raise ValueError("application_onboarding_receipt_tenant_mismatch")
            if receipt.auth_context_ref != self.auth_context_ref:
                raise ValueError("application_onboarding_receipt_auth_context_mismatch")
            if not receipt.completed:
                raise ValueError("application_onboarding_requires_completed_read_receipts")
            if receipt.direct_api_execution_authorized:
                raise ValueError("application_onboarding_cannot_inherit_direct_api_authority")
            for observation in receipt.observations:
                exchange = observation.exchange
                if exchange.application_id != self.application_id:
                    raise ValueError("application_onboarding_observation_application_mismatch")
                if exchange.tenant_scope_ref != self.tenant_scope_ref:
                    raise ValueError("application_onboarding_observation_tenant_mismatch")
                if exchange.auth_context_ref != self.auth_context_ref:
                    raise ValueError("application_onboarding_observation_auth_context_mismatch")
        return self

    def read_is_authoritatively_verified(self) -> bool:
        verification = self.authoritative_read_verification
        if verification is not None:
            return verification.status is EffectVerificationStatus.VERIFIED_APPLIED
        return self.environment_kind is ApplicationEnvironmentKind.SYNTHETIC and self.authoritative_read_verified


class ApplicationProfile(BaseModel):
    contract: str = APPLICATION_ONBOARDING_CONTRACT
    application_id: str
    tenant_scope_ref: str
    environment_kind: ApplicationEnvironmentKind
    allowed_hosts: tuple[str, ...]
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_shape_fingerprints: tuple[str, ...]
    auth_context_bound: bool
    raw_page_urls_retained: bool = False
    raw_secrets_retained: bool = False

    @model_validator(mode="after")
    def profile_is_secret_safe(self) -> "ApplicationProfile":
        if self.raw_page_urls_retained or self.raw_secrets_retained:
            raise ValueError("application_profile_cannot_retain_raw_urls_or_secrets")
        return self


class ReadCapabilityCandidate(BaseModel):
    contract: str = APPLICATION_ONBOARDING_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_name: str = Field(min_length=1)
    application_id: str
    tenant_scope_ref: str
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: OnboardingStatus
    transport_preference: TransportPreference
    observed_api_candidates: tuple[EndpointCandidate, ...] = ()
    procedure_steps: tuple[ProcedureStep, ...] = Field(min_length=1)
    direct_execution_allowed: bool = False
    write_capability_allowed: bool = False
    requires_repeated_verification: bool = True
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def onboarding_never_authorizes_execution_or_writes(self) -> "ReadCapabilityCandidate":
        if self.direct_execution_allowed or self.write_capability_allowed:
            raise ValueError("application_onboarding_never_authorizes_execution_or_write")
        if self.status is OnboardingStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked_application_onboarding_requires_blocker")
        return self


def _shape_fingerprint(url: str | None) -> str | None:
    if not url or url == "about:blank":
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host:
        return None
    payload = {"host": host, "path": parsed.path or "/"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _environment_fingerprint(session: ApplicationOnboardingSession) -> tuple[str, tuple[str, ...]]:
    page_shapes = tuple(
        sorted(
            {
                item
                for receipt in session.receipts
                for item in (_shape_fingerprint(receipt.page_url_after),)
                if item is not None
            }
        )
    )
    observation_shapes = []
    for receipt in session.receipts:
        for observation in receipt.observations:
            exchange = observation.exchange
            observation_shapes.append(
                {
                    "host": exchange.host,
                    "method": exchange.method,
                    "path": exchange.path,
                    "request_schema": observation.request_schema.schema_fingerprint if observation.request_schema else None,
                    "response_schema": observation.response_schema.schema_fingerprint if observation.response_schema else None,
                }
            )
    payload = {
        "contract": APPLICATION_ONBOARDING_CONTRACT,
        "application_id": session.application_id,
        "tenant_scope_ref": session.tenant_scope_ref,
        "environment_kind": session.environment_kind.value,
        "allowed_hosts": sorted(session.allowed_hosts),
        "page_shapes": page_shapes,
        "observation_shapes": sorted(
            observation_shapes,
            key=lambda item: (item["host"], item["path"], item["method"]),
        ),
        "locator_kinds": sorted(receipt.locator_kind.value for receipt in session.receipts),
        "auth_context_bound": True,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return fingerprint, page_shapes


def build_application_profile(session: ApplicationOnboardingSession) -> ApplicationProfile:
    fingerprint, page_shapes = _environment_fingerprint(session)
    return ApplicationProfile(
        application_id=session.application_id,
        tenant_scope_ref=session.tenant_scope_ref,
        environment_kind=session.environment_kind,
        allowed_hosts=tuple(sorted(session.allowed_hosts)),
        environment_fingerprint=fingerprint,
        page_shape_fingerprints=page_shapes,
        auth_context_bound=True,
    )


def _structured_ui_steps(receipts: tuple[BrowserActionReceipt, ...]) -> tuple[ProcedureStep, ...]:
    steps: list[ProcedureStep] = []
    for index, receipt in enumerate(receipts, start=1):
        if receipt.locator_kind in {LocatorKind.ROLE, LocatorKind.LABEL, LocatorKind.PLACEHOLDER}:
            kind = ProcedureStepKind.ACCESSIBILITY
        else:
            kind = ProcedureStepKind.DOM
        steps.append(
            ProcedureStep(
                step_id=f"observe-{index:02d}-{receipt.action_id}",
                kind=kind,
                operation_ref=(
                    f"browser-observation://{receipt.application_id}/"
                    f"{receipt.action_id}/{receipt.action_kind.value}/{receipt.locator_kind.value}"
                ),
                side_effect=False,
            )
        )
    steps.append(
        ProcedureStep(
            step_id="authoritative-readback",
            kind=ProcedureStepKind.READBACK,
            operation_ref="readback://authoritative-application-state",
            side_effect=False,
        )
    )
    return tuple(steps)


def discover_read_capability(
    *,
    session: ApplicationOnboardingSession,
    capability_name: str,
) -> tuple[ApplicationProfile, ReadCapabilityCandidate]:
    if not capability_name.strip():
        raise ValueError("application_onboarding_capability_name_required")
    profile = build_application_profile(session)
    exchanges = [observation.exchange for receipt in session.receipts for observation in receipt.observations]
    candidates = discover_api_candidates(exchanges, allowed_hosts=set(session.allowed_hosts))
    read_candidates = tuple(
        item for item in candidates if item.operation_kind is OperationKind.READ and item.eligible_for_promotion
    )
    write_candidates = tuple(item for item in candidates if item.operation_kind is OperationKind.WRITE)

    blockers: list[str] = []
    if session.business_write_observed or write_candidates:
        blockers.append("application_onboarding_mutating_traffic_observed")
    if any(receipt.capture_errors for receipt in session.receipts):
        blockers.append("application_onboarding_browser_capture_incomplete")
    if any(receipt.ignored_non_allowlisted_response_count for receipt in session.receipts):
        blockers.append("application_onboarding_non_allowlisted_traffic_observed")

    steps = _structured_ui_steps(session.receipts)
    transport = (
        TransportPreference.OBSERVED_READ_API
        if read_candidates
        else (
            TransportPreference.ACCESSIBILITY
            if any(step.kind is ProcedureStepKind.ACCESSIBILITY for step in steps)
            else TransportPreference.DOM
        )
    )
    status = OnboardingStatus.BLOCKED if blockers else OnboardingStatus.READ_CAPABILITY_CANDIDATE
    candidate_payload = {
        "application_id": session.application_id,
        "tenant_scope_ref": session.tenant_scope_ref,
        "capability_name": capability_name,
        "environment_fingerprint": profile.environment_fingerprint,
        "step_fingerprint": procedure_step_fingerprint(steps),
    }
    candidate_id = hashlib.sha256(
        json.dumps(candidate_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return profile, ReadCapabilityCandidate(
        candidate_id=candidate_id,
        capability_name=capability_name,
        application_id=session.application_id,
        tenant_scope_ref=session.tenant_scope_ref,
        environment_fingerprint=profile.environment_fingerprint,
        status=status,
        transport_preference=transport,
        observed_api_candidates=read_candidates,
        procedure_steps=steps,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def create_read_demonstration(
    *,
    session: ApplicationOnboardingSession,
    candidate: ReadCapabilityCandidate,
) -> ProcedureDemonstration:
    if candidate.status is OnboardingStatus.BLOCKED:
        raise ValueError("blocked_onboarding_candidate_cannot_create_demonstration")
    if candidate.environment_fingerprint != build_application_profile(session).environment_fingerprint:
        raise ValueError("onboarding_candidate_environment_mismatch")
    verified = session.read_is_authoritatively_verified()
    return ProcedureDemonstration(
        demonstration_id=f"onboarding:{session.session_id}",
        tenant_id=session.tenant_scope_ref,
        capability_name=candidate.capability_name,
        observed_at=session.observed_at,
        step_fingerprint=procedure_step_fingerprint(candidate.procedure_steps),
        successful=verified,
        effect_verified=verified,
        ambiguous_outcome=False,
        environment_fingerprint=candidate.environment_fingerprint,
        evidence_refs=session.evidence_refs,
    )


def compile_onboarded_read_capability(
    *,
    candidate: ReadCapabilityCandidate,
    demonstrations: list[ProcedureDemonstration],
    version: int = 1,
) -> ProceduralCapability:
    if candidate.status is OnboardingStatus.BLOCKED:
        raise ValueError("blocked_onboarding_candidate_cannot_compile")
    if any(step.side_effect for step in candidate.procedure_steps):
        raise ValueError("read_onboarding_candidate_cannot_contain_side_effect")
    return compile_procedure(
        tenant_id=candidate.tenant_scope_ref,
        capability_name=candidate.capability_name,
        steps=candidate.procedure_steps,
        demonstrations=demonstrations,
        version=version,
        minimum_verified_demonstrations=2,
    )
