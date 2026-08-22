"""Bridge verified Jarvis situations into reviewed read-only swarm objectives.

Situation detection may justify waking research/company-read workers, but it does
not create execution authority. This bridge accepts only an already-proposed
ObjectiveDecompositionProposal that is bound to an enabled reviewed rule, exact
situation evidence and the existing deterministic decomposition admission gate.

Version 1 is intentionally read-only: any pending side-effect lane is rejected.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .objective_decomposition_admission import (
    AdmittedObjectiveDecomposition,
    ObjectiveDecompositionPolicy,
    ObjectiveDecompositionProposal,
    admit_objective_decomposition,
)
from .situation_detection import SituationAttention, SituationCandidate

SITUATION_OBJECTIVE_ADMISSION_CONTRACT = "eay-situation-objective-admission-v1"

_ATTENTION_RANK = {
    SituationAttention.WATCH: 1,
    SituationAttention.SURFACE: 2,
    SituationAttention.ESCALATE: 3,
}


class SituationObjectiveRule(BaseModel):
    contract: str = SITUATION_OBJECTIVE_ADMISSION_CONTRACT
    rule_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    objective_ref_prefix: str = Field(min_length=1)
    required_domains: tuple[str, ...] = Field(min_length=1)
    minimum_attention: SituationAttention = SituationAttention.SURFACE
    minimum_situation_score: float = Field(default=0.60, ge=0.0, le=1.0)
    max_candidate_age_seconds: int = Field(default=900, ge=1, le=86_400)
    review_evidence_ref: str = Field(min_length=1)
    enabled: bool = True
    read_only_only: bool = True
    truth_authority_granted: bool = False
    replanning_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def rule_is_reviewed_read_only_and_non_authoritative(self) -> "SituationObjectiveRule":
        if not self.read_only_only:
            raise ValueError("situation_objective_v1_is_read_only_only")
        if self.truth_authority_granted or self.replanning_authority_granted or self.execution_authority_granted:
            raise ValueError("situation_objective_rule_never_grants_authority")
        if len(self.required_domains) != len(set(self.required_domains)):
            raise ValueError("situation_objective_rule_domains_must_be_unique")
        return self


class SituationObjectiveAdmission(BaseModel):
    contract: str = SITUATION_OBJECTIVE_ADMISSION_CONTRACT
    rule_ref: str
    situation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective_ref: str
    admitted: AdmittedObjectiveDecomposition
    eligible_for_worker_scheduling: bool = True
    truth_authority_granted: bool = False
    replanning_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def admission_is_worker_wakeup_only(self) -> "SituationObjectiveAdmission":
        if self.truth_authority_granted or self.replanning_authority_granted or self.execution_authority_granted:
            raise ValueError("situation_objective_admission_never_grants_authority")
        if not self.eligible_for_worker_scheduling:
            raise ValueError("situation_objective_admission_must_be_schedulable")
        if self.admitted.mutating_lane_count != 0:
            raise ValueError("situation_objective_admission_cannot_contain_mutation")
        if self.objective_ref != self.admitted.plan.objective_ref:
            raise ValueError("situation_objective_admission_objective_mismatch")
        return self


def admit_situation_driven_objective(
    *,
    candidate: SituationCandidate,
    proposal: ObjectiveDecompositionProposal,
    rule: SituationObjectiveRule,
    decomposition_policy: ObjectiveDecompositionPolicy,
    now: datetime,
) -> SituationObjectiveAdmission:
    """Admit a reviewed read-only objective; never execute or replan it here."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("situation_objective_now_requires_timezone")
    candidate = SituationCandidate.model_validate(candidate.model_dump(mode="json"))
    proposal = ObjectiveDecompositionProposal.model_validate(proposal.model_dump(mode="json"))
    rule = SituationObjectiveRule.model_validate(rule.model_dump(mode="json"))

    if not rule.enabled:
        raise ValueError("situation_objective_rule_disabled")
    if candidate.tenant_id != rule.tenant_id or proposal.tenant_id != rule.tenant_id:
        raise ValueError("situation_objective_tenant_mismatch")
    if candidate.detected_at > now:
        raise ValueError("situation_objective_candidate_from_future")
    age = (now - candidate.detected_at).total_seconds()
    if age > rule.max_candidate_age_seconds:
        raise ValueError("situation_objective_candidate_stale")
    if candidate.situation_score < rule.minimum_situation_score:
        raise ValueError("situation_objective_score_below_threshold")
    if _ATTENTION_RANK[candidate.attention] < _ATTENTION_RANK[rule.minimum_attention]:
        raise ValueError("situation_objective_attention_below_threshold")
    if not set(rule.required_domains).issubset(set(candidate.domains)):
        raise ValueError("situation_objective_required_domain_missing")
    if not proposal.objective_ref.startswith(rule.objective_ref_prefix):
        raise ValueError("situation_objective_ref_prefix_mismatch")

    situation_ref = f"situation-candidate://{candidate.fingerprint}"
    required_root_evidence = {situation_ref, rule.review_evidence_ref}
    if not required_root_evidence.issubset(set(proposal.decomposition_evidence_refs)):
        raise ValueError("situation_objective_root_evidence_missing")

    if any(item.lane.has_pending_side_effect() for item in proposal.lanes):
        raise ValueError("situation_objective_v1_forbids_mutating_lane")

    admitted = admit_objective_decomposition(
        proposal=proposal,
        policy=decomposition_policy,
    )
    if admitted.mutating_lane_count:
        raise ValueError("situation_objective_v1_forbids_mutating_lane")

    return SituationObjectiveAdmission(
        rule_ref=rule.rule_ref,
        situation_fingerprint=candidate.fingerprint,
        objective_ref=proposal.objective_ref,
        admitted=admitted,
    )
