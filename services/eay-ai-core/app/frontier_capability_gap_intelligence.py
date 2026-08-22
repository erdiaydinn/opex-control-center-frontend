"""Evidence-bound capability-gap controller for Jarvis Frontier-3 certification.

Frontier certification should drive measurable improvement work, not marketing
language. This layer converts each uncertified domain into deterministic eval,
safety, protocol, evidence or capability work items and verifies later closure only
against a newer sealed Frontier-3 certification artifact.

The controller never trains a model, edits production policy, changes providers,
executes code, promotes Company Truth or upgrades a capability claim by itself.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frontier3_certification_intelligence import (
    Frontier3CertificationArtifact,
    FrontierCertificationDomain,
    FrontierCertificationStatus,
)

FRONTIER_CAPABILITY_GAP_CONTRACT = "eay-frontier-capability-gap-v1"
FRONTIER_CAPABILITY_GAP_CLOSURE_CONTRACT = "eay-frontier-capability-gap-closure-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CapabilityImprovementTarget(str, Enum):
    FRONTIER_PARITY = "frontier_parity"
    MEASURED_SUPERIORITY = "measured_superiority"


class CapabilityGapWorkKind(str, Enum):
    SAFETY_REMEDIATION = "safety_remediation"
    PROTOCOL_REPAIR = "protocol_repair"
    BENCHMARK_REFRESH = "benchmark_refresh"
    PROVIDER_DIVERSITY = "provider_diversity"
    EVALUATION_HARDENING = "evaluation_hardening"
    EVIDENCE_COMPLETION = "evidence_completion"
    CAPABILITY_IMPROVEMENT = "capability_improvement"
    UNCERTAINTY_REDUCTION = "uncertainty_reduction"


class CapabilityImprovementPlanState(str, Enum):
    COMPLETE = "complete"
    OPEN = "open"


class CapabilityGapClosureState(str, Enum):
    CLOSED = "closed"
    NOT_CLOSED = "not_closed"


class CapabilityGapWorkItem(SealedModel):
    work_item_id: str = Field(pattern=_DIGEST)
    domain: FrontierCertificationDomain
    kind: CapabilityGapWorkKind
    source_status: FrontierCertificationStatus
    priority: int = Field(ge=1, le=100)
    objective: str = Field(min_length=12)
    acceptance_criteria: tuple[str, ...] = Field(min_length=1)
    source_blockers: tuple[str, ...]
    raw_score_gap: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...]
    execution_authority_granted: bool = False
    automatic_training_allowed: bool = False
    automatic_code_change_allowed: bool = False

    @model_validator(mode="after")
    def work_item_is_non_authoritative(self) -> "CapabilityGapWorkItem":
        if any(
            (
                self.execution_authority_granted,
                self.automatic_training_allowed,
                self.automatic_code_change_allowed,
            )
        ):
            raise ValueError("capability_gap_work_item_never_mints_execution_or_training_authority")
        return self


class CapabilityImprovementPlan(SealedModel):
    contract: str = FRONTIER_CAPABILITY_GAP_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    jarvis_system_id: str = Field(pattern=_SCOPE)
    source_certification_fingerprint: str = Field(pattern=_DIGEST)
    source_assessed_at: datetime
    target: CapabilityImprovementTarget
    required_domains: tuple[FrontierCertificationDomain, ...]
    target_satisfied_domains: tuple[FrontierCertificationDomain, ...]
    open_domains: tuple[FrontierCertificationDomain, ...]
    work_items: tuple[CapabilityGapWorkItem, ...]
    state: CapabilityImprovementPlanState
    complete_frontier3_matrix: bool
    automatic_training_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    automatic_provider_change_allowed: bool = False
    automatic_code_change_allowed: bool = False
    company_truth_promoted: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    claim_upgrade_allowed: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def plan_is_integral_and_non_authoritative(self) -> "CapabilityImprovementPlan":
        if self.source_assessed_at.tzinfo is None or self.source_assessed_at.utcoffset() is None:
            raise ValueError("capability_gap_source_assessment_requires_timezone")
        if any(
            (
                self.automatic_training_allowed,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.automatic_provider_change_allowed,
                self.automatic_code_change_allowed,
                self.company_truth_promoted,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
                self.claim_upgrade_allowed,
            )
        ):
            raise ValueError("capability_gap_plan_never_mints_change_or_claim_authority")
        if self.state is CapabilityImprovementPlanState.COMPLETE:
            if self.open_domains or self.work_items:
                raise ValueError("capability_gap_complete_plan_cannot_have_open_work")
        elif not self.open_domains:
            raise ValueError("capability_gap_open_plan_requires_open_domain")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("capability_gap_plan_fingerprint_mismatch")
        return self


class CapabilityGapClosureArtifact(SealedModel):
    contract: str = FRONTIER_CAPABILITY_GAP_CLOSURE_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    work_item_id: str = Field(pattern=_DIGEST)
    domain: FrontierCertificationDomain
    target: CapabilityImprovementTarget
    source_plan_fingerprint: str = Field(pattern=_DIGEST)
    source_certification_fingerprint: str = Field(pattern=_DIGEST)
    candidate_certification_fingerprint: str = Field(pattern=_DIGEST)
    candidate_status: FrontierCertificationStatus
    state: CapabilityGapClosureState
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    bounded_gap_closure_claim_allowed: bool
    matrix_claim_upgrade_allowed: bool = False
    automatic_training_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    automatic_provider_change_allowed: bool = False
    automatic_code_change_allowed: bool = False
    company_truth_promoted: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def closure_is_integral_and_non_authoritative(self) -> "CapabilityGapClosureArtifact":
        if any(
            (
                self.matrix_claim_upgrade_allowed,
                self.automatic_training_allowed,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.automatic_provider_change_allowed,
                self.automatic_code_change_allowed,
                self.company_truth_promoted,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("capability_gap_closure_never_mints_change_or_matrix_claim_authority")
        if self.state is CapabilityGapClosureState.CLOSED:
            if self.blockers or not self.bounded_gap_closure_claim_allowed:
                raise ValueError("capability_gap_closed_requires_clean_bounded_claim")
        elif self.bounded_gap_closure_claim_allowed:
            raise ValueError("capability_gap_not_closed_cannot_allow_claim")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("capability_gap_closure_fingerprint_mismatch")
        return self


def _seal(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload(item: BaseModel) -> dict[str, object]:
    return item.model_dump(mode="json", exclude={"fingerprint"})


def _target_met(status: FrontierCertificationStatus, target: CapabilityImprovementTarget) -> bool:
    if target is CapabilityImprovementTarget.FRONTIER_PARITY:
        return status in {
            FrontierCertificationStatus.FRONTIER_PARITY,
            FrontierCertificationStatus.STATISTICALLY_SUPERIOR,
        }
    return status is FrontierCertificationStatus.STATISTICALLY_SUPERIOR


def _work_item_id(
    *,
    source_fingerprint: str,
    domain: FrontierCertificationDomain,
    kind: CapabilityGapWorkKind,
    target: CapabilityImprovementTarget,
) -> str:
    return _seal(
        {
            "source": source_fingerprint,
            "domain": domain.value,
            "kind": kind.value,
            "target": target.value,
        }
    )


def _kinds_for_domain(
    *,
    status: FrontierCertificationStatus,
    blockers: tuple[str, ...],
    target: CapabilityImprovementTarget,
) -> tuple[CapabilityGapWorkKind, ...]:
    kinds: list[CapabilityGapWorkKind] = []
    joined = "\n".join(blockers)
    if "critical_safety" in joined:
        kinds.append(CapabilityGapWorkKind.SAFETY_REMEDIATION)
    if "protocol_mismatch" in joined:
        kinds.append(CapabilityGapWorkKind.PROTOCOL_REPAIR)
    if "benchmark_stale" in joined or "future_measurement" in joined:
        kinds.append(CapabilityGapWorkKind.BENCHMARK_REFRESH)
    if "provider_diversity" in joined or "provider_family" in joined:
        kinds.append(CapabilityGapWorkKind.PROVIDER_DIVERSITY)
    if "measurement_missing" in joined or "no_eligible_frontier_peer" in joined:
        kinds.append(CapabilityGapWorkKind.EVIDENCE_COMPLETION)
    if any(
        token in joined
        for token in (
            "sample_count",
            "confidence_level",
            "scenario_coverage",
            "evaluator_independence",
            "frontier_qualified",
        )
    ):
        kinds.append(CapabilityGapWorkKind.EVALUATION_HARDENING)
    if status is FrontierCertificationStatus.BELOW_FRONTIER:
        kinds.append(CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT)
    if (
        status is FrontierCertificationStatus.FRONTIER_PARITY
        and target is CapabilityImprovementTarget.MEASURED_SUPERIORITY
    ):
        kinds.append(CapabilityGapWorkKind.UNCERTAINTY_REDUCTION)
    if not kinds and status is FrontierCertificationStatus.HOLD:
        kinds.append(CapabilityGapWorkKind.EVIDENCE_COMPLETION)
    return tuple(dict.fromkeys(kinds))


def _priority(kind: CapabilityGapWorkKind, raw_gap: float) -> int:
    base = {
        CapabilityGapWorkKind.SAFETY_REMEDIATION: 100,
        CapabilityGapWorkKind.PROTOCOL_REPAIR: 96,
        CapabilityGapWorkKind.BENCHMARK_REFRESH: 92,
        CapabilityGapWorkKind.EVIDENCE_COMPLETION: 90,
        CapabilityGapWorkKind.PROVIDER_DIVERSITY: 88,
        CapabilityGapWorkKind.EVALUATION_HARDENING: 84,
        CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT: 76,
        CapabilityGapWorkKind.UNCERTAINTY_REDUCTION: 72,
    }[kind]
    if kind is CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT:
        return min(99, base + int(round(raw_gap * 100)))
    return base


def _objective(kind: CapabilityGapWorkKind, domain: FrontierCertificationDomain) -> str:
    label = domain.value.replace("_", " ")
    return {
        CapabilityGapWorkKind.SAFETY_REMEDIATION: f"Eliminate the critical safety regression in {label} before capability claims.",
        CapabilityGapWorkKind.PROTOCOL_REPAIR: f"Restore same-protocol benchmark comparability for {label}.",
        CapabilityGapWorkKind.BENCHMARK_REFRESH: f"Produce fresh as-of-valid benchmark evidence for {label}.",
        CapabilityGapWorkKind.PROVIDER_DIVERSITY: f"Restore at least three independent provider families for {label}.",
        CapabilityGapWorkKind.EVALUATION_HARDENING: f"Strengthen sample depth, scenario coverage and evaluator independence for {label}.",
        CapabilityGapWorkKind.EVIDENCE_COMPLETION: f"Complete the missing admissible certification evidence for {label}.",
        CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT: f"Close the measured performance deficit against the strongest frontier peer in {label}.",
        CapabilityGapWorkKind.UNCERTAINTY_REDUCTION: f"Create confidence-separated evidence for measured superiority in {label}.",
    }[kind]


def _acceptance(
    *,
    kind: CapabilityGapWorkKind,
    target: CapabilityImprovementTarget,
) -> tuple[str, ...]:
    common = (
        "A newer sealed Frontier-3 certification artifact must re-evaluate the same domain.",
        "No critical safety regression may be present.",
        "Benchmark protocol, task set, environment, metric set and as-of boundary must remain comparable.",
    )
    target_rule = (
        "The domain must reach FRONTIER_PARITY or STATISTICALLY_SUPERIOR."
        if target is CapabilityImprovementTarget.FRONTIER_PARITY
        else "The domain must reach STATISTICALLY_SUPERIOR with confidence separation."
    )
    kind_rule = {
        CapabilityGapWorkKind.SAFETY_REMEDIATION: "Independent safety evidence must show the regression is absent.",
        CapabilityGapWorkKind.PROTOCOL_REPAIR: "All admitted Jarvis and frontier measurements must share one exact protocol identity.",
        CapabilityGapWorkKind.BENCHMARK_REFRESH: "All admitted measurements must be within the configured freshness boundary and not from the future.",
        CapabilityGapWorkKind.PROVIDER_DIVERSITY: "At least three eligible measurements must come from distinct provider families.",
        CapabilityGapWorkKind.EVALUATION_HARDENING: "Minimum sample, confidence, holdout/OOD/adversarial/temporal coverage and evaluator independence must pass.",
        CapabilityGapWorkKind.EVIDENCE_COMPLETION: "Missing Jarvis/frontier evidence must be present and eligible.",
        CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT: "Jarvis raw score must no longer be below the strongest eligible frontier score.",
        CapabilityGapWorkKind.UNCERTAINTY_REDUCTION: "Jarvis confidence lower bound must clear all eligible frontier upper bounds under the certification policy.",
    }[kind]
    return (*common, kind_rule, target_rule)


def build_capability_improvement_plan(
    *,
    source: Frontier3CertificationArtifact,
    tenant_id: str,
    company_id: str,
    target: CapabilityImprovementTarget = CapabilityImprovementTarget.FRONTIER_PARITY,
) -> CapabilityImprovementPlan:
    source = Frontier3CertificationArtifact.model_validate(source.model_dump(mode="json"))
    if source.tenant_id != tenant_id:
        raise ValueError("capability_gap_cross_tenant_source_forbidden")
    if source.company_id != company_id:
        raise ValueError("capability_gap_cross_company_source_forbidden")

    satisfied: list[FrontierCertificationDomain] = []
    open_domains: list[FrontierCertificationDomain] = []
    work: list[CapabilityGapWorkItem] = []
    for certification in source.domain_certifications:
        if _target_met(certification.status, target):
            satisfied.append(certification.domain)
            continue
        open_domains.append(certification.domain)
        raw_gap = max(0.0, certification.strongest_frontier_score - certification.jarvis_score)
        for kind in _kinds_for_domain(
            status=certification.status,
            blockers=certification.blockers,
            target=target,
        ):
            work.append(
                CapabilityGapWorkItem(
                    work_item_id=_work_item_id(
                        source_fingerprint=source.fingerprint,
                        domain=certification.domain,
                        kind=kind,
                        target=target,
                    ),
                    domain=certification.domain,
                    kind=kind,
                    source_status=certification.status,
                    priority=_priority(kind, raw_gap),
                    objective=_objective(kind, certification.domain),
                    acceptance_criteria=_acceptance(kind=kind, target=target),
                    source_blockers=certification.blockers,
                    raw_score_gap=round(raw_gap, 6),
                    evidence_refs=certification.evidence_refs,
                )
            )

    work.sort(key=lambda item: (-item.priority, item.domain.value, item.kind.value))
    state = (
        CapabilityImprovementPlanState.COMPLETE
        if not open_domains
        else CapabilityImprovementPlanState.OPEN
    )
    values = {
        "contract": FRONTIER_CAPABILITY_GAP_CONTRACT,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "jarvis_system_id": source.jarvis_system_id,
        "source_certification_fingerprint": source.fingerprint,
        "source_assessed_at": source.assessed_at,
        "target": target,
        "required_domains": source.required_domains,
        "target_satisfied_domains": tuple(satisfied),
        "open_domains": tuple(open_domains),
        "work_items": tuple(work),
        "state": state,
        "complete_frontier3_matrix": source.complete_frontier3_matrix,
        "automatic_training_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "automatic_provider_change_allowed": False,
        "automatic_code_change_allowed": False,
        "company_truth_promoted": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
        "claim_upgrade_allowed": False,
    }
    draft = CapabilityImprovementPlan.model_construct(**values, fingerprint="0" * 64)
    return CapabilityImprovementPlan(**values, fingerprint=_seal(_payload(draft)))


def verify_capability_gap_closure(
    *,
    plan: CapabilityImprovementPlan,
    work_item_id: str,
    candidate: Frontier3CertificationArtifact,
    tenant_id: str,
    company_id: str,
) -> CapabilityGapClosureArtifact:
    plan = CapabilityImprovementPlan.model_validate(plan.model_dump(mode="json"))
    candidate = Frontier3CertificationArtifact.model_validate(candidate.model_dump(mode="json"))
    if plan.tenant_id != tenant_id or candidate.tenant_id != tenant_id:
        raise ValueError("capability_gap_closure_cross_tenant_forbidden")
    if plan.company_id != company_id or candidate.company_id != company_id:
        raise ValueError("capability_gap_closure_cross_company_forbidden")
    if candidate.jarvis_system_id != plan.jarvis_system_id:
        raise ValueError("capability_gap_closure_jarvis_system_mismatch")
    if candidate.fingerprint == plan.source_certification_fingerprint:
        raise ValueError("capability_gap_closure_requires_new_certification")
    if candidate.assessed_at <= plan.source_assessed_at:
        raise ValueError("capability_gap_closure_candidate_must_be_newer")

    work_item = next((item for item in plan.work_items if item.work_item_id == work_item_id), None)
    if work_item is None:
        raise ValueError("capability_gap_closure_unknown_work_item")

    certification = next(
        (item for item in candidate.domain_certifications if item.domain is work_item.domain),
        None,
    )
    blockers: list[str] = []
    if certification is None:
        candidate_status = FrontierCertificationStatus.HOLD
        evidence_refs: tuple[str, ...] = ()
        blockers.append("capability_gap_closure_domain_missing")
    else:
        candidate_status = certification.status
        evidence_refs = certification.evidence_refs
        if not _target_met(candidate_status, plan.target):
            blockers.append("capability_gap_closure_target_not_met")

    state = CapabilityGapClosureState.NOT_CLOSED if blockers else CapabilityGapClosureState.CLOSED
    values = {
        "contract": FRONTIER_CAPABILITY_GAP_CLOSURE_CONTRACT,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "work_item_id": work_item_id,
        "domain": work_item.domain,
        "target": plan.target,
        "source_plan_fingerprint": plan.fingerprint,
        "source_certification_fingerprint": plan.source_certification_fingerprint,
        "candidate_certification_fingerprint": candidate.fingerprint,
        "candidate_status": candidate_status,
        "state": state,
        "blockers": tuple(blockers),
        "evidence_refs": evidence_refs,
        "bounded_gap_closure_claim_allowed": state is CapabilityGapClosureState.CLOSED,
        "matrix_claim_upgrade_allowed": False,
        "automatic_training_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "automatic_provider_change_allowed": False,
        "automatic_code_change_allowed": False,
        "company_truth_promoted": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
    }
    draft = CapabilityGapClosureArtifact.model_construct(**values, fingerprint="0" * 64)
    return CapabilityGapClosureArtifact(**values, fingerprint=_seal(_payload(draft)))
