"""Governed discovery and admission registry for Jarvis agentic resources.

Jarvis may discover A2A agents, MCP servers, reusable skills, and OpenAPI
capabilities at runtime, but discovery never grants execution authority. A
resource becomes usable only after identity/version pinning, supply-chain and
license review, evidence-backed evaluation, and policy admission.

Mutating resources are held to the same EAY truth boundary as native
capabilities: idempotent-write semantics plus authoritative effect verification
must be declared and independently evidenced before approval.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

AGENT_RESOURCE_REGISTRY_CONTRACT = "eay-agent-resource-registry-v1"
_SHA40 = re.compile(r"^[a-f0-9]{40}$")


class AgentResourceKind(str, Enum):
    A2A_AGENT = "a2a_agent"
    MCP_SERVER = "mcp_server"
    SKILL = "skill"
    OPENAPI = "openapi"


class AgentResourceLifecycle(str, Enum):
    DISCOVERED = "discovered"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    PUBLISHED = "published"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class AgentResourceSecurity(BaseModel):
    license_approved: bool = False
    supply_chain_verified: bool = False
    source_signature_verified: bool = False
    mutating: bool = False
    user_delegated_auth_required: bool = False
    raw_secrets_retained: bool = False
    model_can_self_authorize: bool = False
    authoritative_effect_verification: bool = False
    idempotent_write: bool = False

    @model_validator(mode="after")
    def security_boundary_is_safe(self) -> "AgentResourceSecurity":
        if self.raw_secrets_retained:
            raise ValueError("agent_resource_cannot_retain_raw_secrets")
        if self.model_can_self_authorize:
            raise ValueError("agent_resource_model_cannot_self_authorize")
        return self


class AgentResourceEvaluation(BaseModel):
    category: str = Field(min_length=1)
    benchmark: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    evidence_ref: str = Field(min_length=1)
    environment_fingerprint: str = Field(min_length=16)
    observed_at: datetime

    @model_validator(mode="after")
    def evaluation_requires_timezone(self) -> "AgentResourceEvaluation":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("agent_resource_evaluation_requires_timezone")
        return self


class AgentResourceRecord(BaseModel):
    contract: str = AGENT_RESOURCE_REGISTRY_CONTRACT
    namespace: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: AgentResourceKind
    source_ref: str = Field(min_length=1)
    source_commit: str = Field(min_length=40, max_length=40)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    capabilities: frozenset[str] = Field(min_length=1)
    protocols: frozenset[str] = Field(min_length=1)
    dependencies: tuple[str, ...] = ()
    lifecycle: AgentResourceLifecycle = AgentResourceLifecycle.DISCOVERED
    security: AgentResourceSecurity = Field(default_factory=AgentResourceSecurity)
    evaluations: tuple[AgentResourceEvaluation, ...] = ()
    reviewed_at: datetime
    immutable_after_evaluation: bool = True

    @model_validator(mode="after")
    def record_is_pinned_and_time_bounded(self) -> "AgentResourceRecord":
        if not _SHA40.fullmatch(self.source_commit):
            raise ValueError("agent_resource_source_commit_must_be_pinned_sha")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("agent_resource_review_requires_timezone")
        if self.lifecycle in {
            AgentResourceLifecycle.EVALUATED,
            AgentResourceLifecycle.APPROVED,
            AgentResourceLifecycle.PUBLISHED,
        } and not self.evaluations:
            raise ValueError("agent_resource_promoted_state_requires_evaluation")
        if not self.immutable_after_evaluation:
            raise ValueError("agent_resource_identity_must_freeze_after_evaluation")
        return self

    @property
    def resource_ref(self) -> str:
        return f"{self.kind.value}://{self.namespace}/{self.name}@{self.version}"


class AgentResourceAdmissionPolicy(BaseModel):
    allowed_kinds: frozenset[AgentResourceKind] = frozenset(AgentResourceKind)
    minimum_safety_score: float = Field(default=0.90, ge=0.0, le=1.0)
    minimum_reliability_score: float = Field(default=0.90, ge=0.0, le=1.0)
    max_evaluation_age_days: int = Field(default=30, ge=1, le=365)
    require_license_approval: bool = True
    require_supply_chain_verification: bool = True
    require_source_signature_for_mutation: bool = True
    unreviewed_public_discovery_allowed: bool = False


class AgentResourceAdmissionDecision(BaseModel):
    contract: str = AGENT_RESOURCE_REGISTRY_CONTRACT
    resource_ref: str
    admitted: bool
    blockers: tuple[str, ...] = ()
    qualifying_evidence_refs: tuple[str, ...] = ()
    discovery_only: bool = True
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def decision_never_grants_authority(self) -> "AgentResourceAdmissionDecision":
        if self.execution_authority_granted:
            raise ValueError("agent_resource_registry_never_grants_execution_authority")
        if self.admitted and self.blockers:
            raise ValueError("agent_resource_admitted_with_blockers")
        return self


def _fresh_evaluations(
    record: AgentResourceRecord,
    *,
    now: datetime,
    policy: AgentResourceAdmissionPolicy,
) -> tuple[AgentResourceEvaluation, ...]:
    max_age = timedelta(days=policy.max_evaluation_age_days)
    return tuple(
        item for item in record.evaluations
        if timedelta(0) <= now - item.observed_at <= max_age
    )


def evaluate_agent_resource_admission(
    *,
    record: AgentResourceRecord,
    policy: AgentResourceAdmissionPolicy,
    now: datetime,
) -> AgentResourceAdmissionDecision:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("agent_resource_admission_requires_timezone")

    blockers: list[str] = []
    evidence_refs: list[str] = []

    if record.kind not in policy.allowed_kinds:
        blockers.append("agent_resource_kind_not_allowed")
    if record.lifecycle not in {
        AgentResourceLifecycle.APPROVED,
        AgentResourceLifecycle.PUBLISHED,
    }:
        blockers.append("agent_resource_not_approved")
    if policy.require_license_approval and not record.security.license_approved:
        blockers.append("agent_resource_license_not_approved")
    if policy.require_supply_chain_verification and not record.security.supply_chain_verified:
        blockers.append("agent_resource_supply_chain_unverified")

    fresh = _fresh_evaluations(record, now=now, policy=policy)
    by_category = {item.category.casefold(): item for item in fresh}
    safety = by_category.get("safety")
    reliability = by_category.get("reliability")
    if safety is None or safety.score < policy.minimum_safety_score:
        blockers.append("agent_resource_safety_evidence_insufficient")
    elif safety.evidence_ref:
        evidence_refs.append(safety.evidence_ref)
    if reliability is None or reliability.score < policy.minimum_reliability_score:
        blockers.append("agent_resource_reliability_evidence_insufficient")
    elif reliability.evidence_ref:
        evidence_refs.append(reliability.evidence_ref)

    if record.security.mutating:
        if policy.require_source_signature_for_mutation and not record.security.source_signature_verified:
            blockers.append("agent_resource_mutating_source_signature_unverified")
        if not record.security.idempotent_write:
            blockers.append("agent_resource_mutating_write_not_idempotent")
        if not record.security.authoritative_effect_verification:
            blockers.append("agent_resource_mutating_effect_verification_missing")

    return AgentResourceAdmissionDecision(
        resource_ref=record.resource_ref,
        admitted=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        qualifying_evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        discovery_only=True,
    )


_ALLOWED_TRANSITIONS: dict[AgentResourceLifecycle, frozenset[AgentResourceLifecycle]] = {
    AgentResourceLifecycle.DISCOVERED: frozenset({AgentResourceLifecycle.EVALUATED, AgentResourceLifecycle.REJECTED}),
    AgentResourceLifecycle.EVALUATED: frozenset({AgentResourceLifecycle.APPROVED, AgentResourceLifecycle.REJECTED}),
    AgentResourceLifecycle.APPROVED: frozenset({AgentResourceLifecycle.PUBLISHED, AgentResourceLifecycle.SUSPENDED}),
    AgentResourceLifecycle.PUBLISHED: frozenset({AgentResourceLifecycle.SUSPENDED}),
    AgentResourceLifecycle.SUSPENDED: frozenset({AgentResourceLifecycle.APPROVED, AgentResourceLifecycle.REJECTED}),
    AgentResourceLifecycle.REJECTED: frozenset(),
}


def transition_agent_resource(
    record: AgentResourceRecord,
    *,
    target: AgentResourceLifecycle,
) -> AgentResourceRecord:
    if target not in _ALLOWED_TRANSITIONS[record.lifecycle]:
        raise ValueError("agent_resource_invalid_lifecycle_transition")
    if target in {
        AgentResourceLifecycle.EVALUATED,
        AgentResourceLifecycle.APPROVED,
        AgentResourceLifecycle.PUBLISHED,
    } and not record.evaluations:
        raise ValueError("agent_resource_transition_requires_evaluation")
    return record.model_copy(update={"lifecycle": target})


def discover_agent_resources(
    *,
    records: tuple[AgentResourceRecord, ...],
    query: str,
    policy: AgentResourceAdmissionPolicy,
    now: datetime,
) -> tuple[AgentResourceRecord, ...]:
    tokens = {token.casefold() for token in re.findall(r"[\w.-]+", query) if token.strip()}
    if not tokens:
        return ()

    ranked: list[tuple[int, AgentResourceRecord]] = []
    for record in records:
        decision = evaluate_agent_resource_admission(record=record, policy=policy, now=now)
        if not decision.admitted:
            continue
        haystack = {
            record.name.casefold(),
            record.namespace.casefold(),
            *(item.casefold() for item in record.capabilities),
            *(item.casefold() for item in record.protocols),
        }
        text = " ".join(haystack)
        score = sum(1 for token in tokens if token in text)
        if score:
            ranked.append((score, record))

    ranked.sort(key=lambda item: (-item[0], item[1].resource_ref))
    return tuple(item[1] for item in ranked)
