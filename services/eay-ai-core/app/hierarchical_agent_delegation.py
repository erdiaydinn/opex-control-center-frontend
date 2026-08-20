"""Bounded parent/child delegation for Jarvis worker swarms.

This is the command bridge behind requests such as "hire agents".  A parent may
delegate a subtree budget to child agents, but cannot amplify its own authority,
escape its tenant, create unbounded recursion, or turn delegation into business
execution permission.  Admitted children become ordinary canonical swarm workers;
the existing scheduler, leases, mission runtime and fan-in remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .parallel_mission_scheduler import LaneSchedulingClass
from .swarm_worker_registry import (
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
)

HIERARCHICAL_AGENT_DELEGATION_CONTRACT = "eay-hierarchical-agent-delegation-v1"


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


class DelegatedAgentState(str, Enum):
    AVAILABLE = "available"
    DRAINING = "draining"
    REVOKED = "revoked"


class AgentCandidate(BaseModel):
    agent_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    worker_class: SwarmWorkerClass
    scheduling_classes: tuple[LaneSchedulingClass, ...] = Field(min_length=1)
    capability_refs: tuple[str, ...] = ()
    provider_key: str = Field(min_length=1)
    attestation_ref: str = Field(min_length=1)
    attestation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attested_until: datetime
    state: DelegatedAgentState = DelegatedAgentState.AVAILABLE
    may_delegate: bool = False
    authority_scope_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def candidate_is_well_formed(self) -> AgentCandidate:
        _aware(self.attested_until, "delegated_agent_attestation_expiry_requires_timezone")
        if len(self.scheduling_classes) != len(set(self.scheduling_classes)):
            raise ValueError("delegated_agent_scheduling_classes_must_be_unique")
        if len(self.capability_refs) != len(set(self.capability_refs)):
            raise ValueError("delegated_agent_capabilities_must_be_unique")
        if len(self.authority_scope_refs) != len(set(self.authority_scope_refs)):
            raise ValueError("delegated_agent_authority_scopes_must_be_unique")
        return self


class AgentDelegationRequest(BaseModel):
    objective_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    parent_session_ref: str = Field(min_length=1)
    parent_agent_id: str = Field(min_length=1)
    delegation_depth: int = Field(ge=1, le=32)
    requested_agent_count: int = Field(ge=1, le=512)
    required_worker_classes: tuple[SwarmWorkerClass, ...] = ()
    required_capability_refs: tuple[str, ...] = ()
    allowed_authority_scope_refs: tuple[str, ...] = ()
    subtree_cost_budget: int = Field(ge=1, le=100_000_000)
    subtree_transition_budget: int = Field(ge=1, le=1_000_000)
    user_command_evidence_ref: str = Field(min_length=1)
    cancellation_token_ref: str = Field(min_length=1)
    children_may_delegate: bool = False
    business_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def request_cannot_grant_authority(self) -> AgentDelegationRequest:
        if self.business_execution_authority_granted:
            raise ValueError("agent_delegation_never_grants_business_execution_authority")
        for values, error in (
            (self.required_worker_classes, "agent_delegation_worker_classes_must_be_unique"),
            (self.required_capability_refs, "agent_delegation_capabilities_must_be_unique"),
            (self.allowed_authority_scope_refs, "agent_delegation_authority_scopes_must_be_unique"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(error)
        return self


class AgentDelegationPolicy(BaseModel):
    max_depth: int = Field(default=3, ge=1, le=16)
    max_agents_per_request: int = Field(default=16, ge=1, le=512)
    max_subtree_cost_budget: int = Field(default=50_000, ge=1, le=100_000_000)
    max_subtree_transition_budget: int = Field(default=10_000, ge=1, le=1_000_000)
    lease_ttl_seconds: int = Field(default=900, ge=30, le=86_400)
    allow_recursive_delegation: bool = False
    require_provider_diversity_above: int = Field(default=1, ge=1, le=512)


class HiredAgentLease(BaseModel):
    lease_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective_ref: str
    tenant_id: str
    parent_session_ref: str
    parent_agent_id: str
    child_agent_id: str
    delegation_depth: int
    capability_refs: tuple[str, ...]
    authority_scope_refs: tuple[str, ...]
    cancellation_token_ref: str
    acquired_at: datetime
    expires_at: datetime
    child_cost_budget: int = Field(ge=1)
    child_transition_budget: int = Field(ge=1)
    may_delegate: bool = False
    business_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def lease_is_bounded(self) -> HiredAgentLease:
        _aware(self.acquired_at, "hired_agent_acquired_at_requires_timezone")
        _aware(self.expires_at, "hired_agent_expires_at_requires_timezone")
        if self.expires_at <= self.acquired_at:
            raise ValueError("hired_agent_expiry_must_follow_acquisition")
        if self.business_execution_authority_granted:
            raise ValueError("hired_agent_lease_never_grants_business_execution_authority")
        return self


class AgentDelegationAdmission(BaseModel):
    contract: str = HIERARCHICAL_AGENT_DELEGATION_CONTRACT
    objective_ref: str
    tenant_id: str
    leases: tuple[HiredAgentLease, ...]
    registry: SwarmWorkerRegistry
    total_cost_budget: int
    total_transition_budget: int
    cancellation_token_ref: str
    admission_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    business_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def admission_is_consistent(self) -> AgentDelegationAdmission:
        if self.business_execution_authority_granted:
            raise ValueError("agent_delegation_admission_never_grants_business_execution_authority")
        if {item.child_agent_id for item in self.leases} != {item.worker_id for item in self.registry.workers}:
            raise ValueError("agent_delegation_registry_lease_mismatch")
        if sum(item.child_cost_budget for item in self.leases) != self.total_cost_budget:
            raise ValueError("agent_delegation_cost_budget_mismatch")
        if sum(item.child_transition_budget for item in self.leases) != self.total_transition_budget:
            raise ValueError("agent_delegation_transition_budget_mismatch")
        return self


def admit_agent_delegation(
    *,
    request: AgentDelegationRequest,
    candidates: tuple[AgentCandidate, ...],
    policy: AgentDelegationPolicy,
    now: datetime,
) -> AgentDelegationAdmission:
    """Hire attested logical agents without creating a second scheduler."""

    _aware(now, "agent_delegation_now_requires_timezone")
    if request.delegation_depth > policy.max_depth:
        raise ValueError("agent_delegation_depth_exceeded")
    if request.requested_agent_count > policy.max_agents_per_request:
        raise ValueError("agent_delegation_agent_count_exceeded")
    if request.subtree_cost_budget > policy.max_subtree_cost_budget:
        raise ValueError("agent_delegation_cost_budget_exceeded")
    if request.subtree_transition_budget > policy.max_subtree_transition_budget:
        raise ValueError("agent_delegation_transition_budget_exceeded")
    if request.children_may_delegate and not policy.allow_recursive_delegation:
        raise ValueError("agent_recursive_delegation_forbidden")

    ids = [item.agent_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("agent_candidate_ids_must_be_unique")
    required_classes = set(request.required_worker_classes)
    required_capabilities = set(request.required_capability_refs)
    allowed_scopes = set(request.allowed_authority_scope_refs)
    eligible = [
        item
        for item in candidates
        if item.tenant_id == request.tenant_id
        and item.state is DelegatedAgentState.AVAILABLE
        and item.attested_until > now
        and (not required_classes or item.worker_class in required_classes)
        and required_capabilities.issubset(set(item.capability_refs))
        and set(item.authority_scope_refs).issubset(allowed_scopes)
        and (not request.children_may_delegate or item.may_delegate)
    ]
    eligible.sort(key=lambda item: (item.provider_key, item.agent_id))
    if len(eligible) < request.requested_agent_count:
        raise ValueError("agent_delegation_insufficient_attested_candidates")
    selected = eligible[: request.requested_agent_count]
    if (
        request.requested_agent_count > policy.require_provider_diversity_above
        and len({item.provider_key for item in selected}) < 2
    ):
        raise ValueError("agent_delegation_provider_diversity_required")

    count = len(selected)
    cost_base, cost_extra = divmod(request.subtree_cost_budget, count)
    transition_base, transition_extra = divmod(request.subtree_transition_budget, count)
    leases: list[HiredAgentLease] = []
    workers: list[SwarmWorkerDescriptor] = []
    for index, item in enumerate(selected):
        child_cost = cost_base + (1 if index < cost_extra else 0)
        child_transitions = transition_base + (1 if index < transition_extra else 0)
        payload = {
            "objective_ref": request.objective_ref,
            "tenant_id": request.tenant_id,
            "parent_session_ref": request.parent_session_ref,
            "parent_agent_id": request.parent_agent_id,
            "child_agent_id": item.agent_id,
            "depth": request.delegation_depth,
            "attestation": item.attestation_fingerprint,
            "command": request.user_command_evidence_ref,
            "cancellation": request.cancellation_token_ref,
            "acquired_at": now.isoformat(),
        }
        leases.append(HiredAgentLease(
            lease_id=_hash(payload),
            objective_ref=request.objective_ref,
            tenant_id=request.tenant_id,
            parent_session_ref=request.parent_session_ref,
            parent_agent_id=request.parent_agent_id,
            child_agent_id=item.agent_id,
            delegation_depth=request.delegation_depth,
            capability_refs=item.capability_refs,
            authority_scope_refs=item.authority_scope_refs,
            cancellation_token_ref=request.cancellation_token_ref,
            acquired_at=now,
            expires_at=min(now + timedelta(seconds=policy.lease_ttl_seconds), item.attested_until),
            child_cost_budget=child_cost,
            child_transition_budget=child_transitions,
            may_delegate=request.children_may_delegate,
        ))
        workers.append(SwarmWorkerDescriptor(
            worker_id=item.agent_id,
            tenant_id=item.tenant_id,
            worker_class=item.worker_class,
            supported_scheduling_classes=item.scheduling_classes,
            capability_refs=item.capability_refs,
        ))

    registry = SwarmWorkerRegistry(tenant_id=request.tenant_id, workers=tuple(workers))
    admission_payload = {
        "contract": HIERARCHICAL_AGENT_DELEGATION_CONTRACT,
        "objective_ref": request.objective_ref,
        "tenant_id": request.tenant_id,
        "lease_ids": [item.lease_id for item in leases],
        "cost": request.subtree_cost_budget,
        "transitions": request.subtree_transition_budget,
        "cancellation": request.cancellation_token_ref,
    }
    return AgentDelegationAdmission(
        objective_ref=request.objective_ref,
        tenant_id=request.tenant_id,
        leases=tuple(leases),
        registry=registry,
        total_cost_budget=request.subtree_cost_budget,
        total_transition_budget=request.subtree_transition_budget,
        cancellation_token_ref=request.cancellation_token_ref,
        admission_fingerprint=_hash(admission_payload),
    )
