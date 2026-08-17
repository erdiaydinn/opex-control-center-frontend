"""Promotion gates from discovered HTTP evidence to a governed Jarvis capability.

Discovery is deliberately easier than execution. A browser may reveal an
endpoint during a legitimate user action, but Jarvis must not immediately turn
that observation into a production mutation tool. This module defines the
minimum evidence required to promote a discovered endpoint while preserving
EAY tenant, approval, idempotency, audit and effect-verification boundaries.

No network I/O is performed here.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .api_discovery_intelligence import EndpointCandidate, OperationKind

API_CAPABILITY_CONTRACT = "eay-api-capability-promotion-v1"


class ValidationEnvironment(str, Enum):
    OBSERVATION_ONLY = "observation_only"
    SANDBOX = "sandbox"
    STAGING = "staging"


class CapabilityState(str, Enum):
    BLOCKED = "blocked"
    INVESTIGATE = "investigate"
    READY_FOR_APPROVAL = "ready_for_approval"
    ACTIVE = "active"


class IdempotencyStrategy(str, Enum):
    NONE = "none"
    IDEMPOTENCY_KEY = "idempotency_key"
    NATURAL_REQUEST_KEY = "natural_request_key"
    READ_BEFORE_WRITE = "read_before_write"
    EXACT_EFFECT_DEDUP = "exact_effect_dedup"


class ApiCapabilityEvidence(BaseModel):
    contract: str = API_CAPABILITY_CONTRACT
    candidate: EndpointCandidate
    capability_name: str = Field(min_length=3)
    business_object: str = Field(min_length=2)
    request_schema_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    response_schema_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    semantic_mapping_verified: bool = False
    authorization_scope_verified: bool = False
    tenant_scope_verified: bool = False
    schema_stability_verified: bool = False
    validation_environment: ValidationEnvironment = ValidationEnvironment.OBSERVATION_ONLY
    non_destructive_validation_passed: bool = False
    gui_api_equivalence_verified: bool = False
    effect_verifier_defined: bool = False
    effect_verifier_ref: str | None = None
    idempotency_strategy: IdempotencyStrategy = IdempotencyStrategy.NONE
    approval_required: bool = False
    approval_evidence_ref: str | None = None
    audit_contract_ref: str | None = None
    rollback_or_compensation_ref: str | None = None

    @model_validator(mode="after")
    def evidence_refs_match_claims(self) -> "ApiCapabilityEvidence":
        if self.effect_verifier_defined and not self.effect_verifier_ref:
            raise ValueError("api_capability_effect_verifier_reference_required")
        if self.approval_evidence_ref and not self.approval_required:
            raise ValueError("api_capability_approval_reference_without_requirement")
        return self


class ApiCapabilityDecision(BaseModel):
    contract: str = API_CAPABILITY_CONTRACT
    capability_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_name: str
    state: CapabilityState
    risk: str
    production_execution_permitted: bool = False
    blockers: tuple[str, ...] = ()
    required_runtime_guards: tuple[str, ...] = ()

    @model_validator(mode="after")
    def execution_cannot_ignore_blockers(self) -> "ApiCapabilityDecision":
        if self.production_execution_permitted and self.blockers:
            raise ValueError("api_capability_execution_cannot_ignore_blockers")
        if self.production_execution_permitted and self.state is not CapabilityState.ACTIVE:
            raise ValueError("api_capability_execution_requires_active_state")
        return self


def _capability_id(evidence: ApiCapabilityEvidence) -> str:
    canonical = json.dumps(
        {
            "candidate_id": evidence.candidate.candidate_id,
            "capability_name": evidence.capability_name,
            "business_object": evidence.business_object,
            "request_schema_fingerprint": evidence.request_schema_fingerprint,
            "response_schema_fingerprint": evidence.response_schema_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_api_capability(evidence: ApiCapabilityEvidence) -> ApiCapabilityDecision:
    candidate = evidence.candidate
    blockers: list[str] = []

    if not candidate.eligible_for_promotion:
        blockers.extend(candidate.blockers or ("api_candidate_not_promotion_eligible",))
    if not evidence.semantic_mapping_verified:
        blockers.append("api_capability_semantics_not_verified")
    if not evidence.authorization_scope_verified:
        blockers.append("api_capability_authorization_scope_not_verified")
    if not evidence.tenant_scope_verified:
        blockers.append("api_capability_tenant_scope_not_verified")
    if not evidence.schema_stability_verified:
        blockers.append("api_capability_schema_stability_not_verified")
    if not evidence.request_schema_fingerprint:
        blockers.append("api_capability_request_schema_missing")
    if not evidence.response_schema_fingerprint:
        blockers.append("api_capability_response_schema_missing")
    if not evidence.audit_contract_ref:
        blockers.append("api_capability_audit_contract_missing")

    runtime_guards = [
        "fresh_user_or_governed_mission_intent",
        "exact_application_host_allowlist",
        "managed_session_auth_context",
        "tenant_scope_recheck_before_execution",
        "request_fingerprint_audit",
        "response_fingerprint_audit",
    ]

    if candidate.operation_kind is OperationKind.WRITE:
        if evidence.validation_environment not in {ValidationEnvironment.SANDBOX, ValidationEnvironment.STAGING}:
            blockers.append("api_write_requires_non_production_validation_environment")
        if not evidence.non_destructive_validation_passed:
            blockers.append("api_write_non_destructive_validation_missing")
        if not evidence.gui_api_equivalence_verified:
            blockers.append("api_write_gui_api_equivalence_not_verified")
        if not evidence.effect_verifier_defined:
            blockers.append("api_write_effect_verifier_missing")
        if evidence.idempotency_strategy is IdempotencyStrategy.NONE:
            blockers.append("api_write_idempotency_strategy_missing")
        if not evidence.rollback_or_compensation_ref:
            blockers.append("api_write_rollback_or_compensation_missing")
        runtime_guards.extend(
            [
                "read_before_write_when_supported",
                "single_submit_guard",
                "postcondition_effect_verification",
                "duplicate_effect_detection",
                "halt_on_ambiguous_outcome",
            ]
        )

    if candidate.operation_kind is OperationKind.UNKNOWN:
        blockers.append("api_capability_unknown_operation_kind")

    approval_pending = evidence.approval_required and not evidence.approval_evidence_ref
    if approval_pending:
        blockers.append("api_capability_required_approval_missing")

    unique_blockers = tuple(dict.fromkeys(blockers))
    if unique_blockers:
        state = CapabilityState.BLOCKED if candidate.operation_kind is OperationKind.WRITE else CapabilityState.INVESTIGATE
    elif evidence.approval_required:
        state = CapabilityState.ACTIVE
    else:
        state = CapabilityState.ACTIVE

    risk = "mutating" if candidate.operation_kind is OperationKind.WRITE else "read_only"
    return ApiCapabilityDecision(
        capability_id=_capability_id(evidence),
        capability_name=evidence.capability_name,
        state=state,
        risk=risk,
        production_execution_permitted=not unique_blockers and state is CapabilityState.ACTIVE,
        blockers=unique_blockers,
        required_runtime_guards=tuple(runtime_guards),
    )
