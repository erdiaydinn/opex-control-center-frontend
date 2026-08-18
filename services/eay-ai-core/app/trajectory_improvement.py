"""Offline, evidence-bound improvement proposals for Jarvis agent trajectories.

Inspired by symbolic/trajectory-learning research, but intentionally safer for
enterprise production: observed failures may produce a *reviewable revision
candidate*, never a self-modification.  The candidate must pass JarvisBench,
independent review and human approval before a canary is allowed.  This module
never activates a production prompt, tool, workflow, router or verifier.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel, Field, model_validator

TRAJECTORY_IMPROVEMENT_CONTRACT = "eay-trajectory-improvement-v1"


class EvaluationEnvironment(str, Enum):
    SYNTHETIC = "synthetic"
    STAGING = "staging"
    REDACTED_PRODUCTION_EVIDENCE = "redacted_production_evidence"


class ImprovementTarget(str, Enum):
    PROMPT_POLICY = "prompt_policy"
    TOOL_SELECTION = "tool_selection"
    WORKFLOW_GRAPH = "workflow_graph"
    ROUTING_POLICY = "routing_policy"
    EFFECT_VERIFIER = "effect_verifier"
    MEMORY_POLICY = "memory_policy"


class ImprovementStatus(str, Enum):
    CANDIDATE = "candidate"
    BLOCKED = "blocked"
    APPROVED_FOR_CANARY = "approved_for_canary"


class OfflineTrajectoryEvaluation(BaseModel):
    contract: str = TRAJECTORY_IMPROVEMENT_CONTRACT
    evaluation_id: str = Field(min_length=1)
    trace_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1)
    environment: EvaluationEnvironment
    evaluator_ref: str = Field(min_length=1)
    outcome_score: float = Field(ge=0.0, le=1.0)
    failure_classes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    ambiguous_side_effect_observed: bool = False
    raw_trace_content_retained: bool = False
    secret_values_retained: bool = False

    @model_validator(mode="after")
    def evaluation_is_safe_and_actionable(self) -> "OfflineTrajectoryEvaluation":
        if self.raw_trace_content_retained or self.secret_values_retained:
            raise ValueError("trajectory_evaluation_cannot_retain_raw_or_secret_content")
        if self.outcome_score >= 0.999 and not self.failure_classes and not self.ambiguous_side_effect_observed:
            raise ValueError("trajectory_evaluation_has_no_improvement_signal")
        return self


class ImprovementCandidate(BaseModel):
    contract: str = TRAJECTORY_IMPROVEMENT_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str
    target: ImprovementTarget
    revision_artifact_ref: str = Field(min_length=1)
    source_trace_ids: tuple[str, ...] = Field(min_length=1)
    evaluation_refs: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    status: ImprovementStatus = ImprovementStatus.CANDIDATE
    jarvisbench_required: bool = True
    independent_review_required: bool = True
    human_approval_required: bool = True
    automatic_self_modification_allowed: bool = False
    production_activation_allowed: bool = False
    canary_activation_allowed: bool = False

    @model_validator(mode="after")
    def candidate_never_self_promotes(self) -> "ImprovementCandidate":
        if self.automatic_self_modification_allowed:
            raise ValueError("trajectory_improvement_self_modification_forbidden")
        if self.production_activation_allowed or self.canary_activation_allowed:
            raise ValueError("unvalidated_trajectory_candidate_cannot_activate")
        if not self.jarvisbench_required or not self.independent_review_required or not self.human_approval_required:
            raise ValueError("trajectory_candidate_cannot_remove_promotion_gates")
        return self


class ImprovementValidationEvidence(BaseModel):
    contract: str = TRAJECTORY_IMPROVEMENT_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    jarvisbench_evidence_ref: str | None = None
    jarvisbench_passed: bool = False
    minimum_sample_count: int = Field(default=0, ge=0)
    no_safety_regression: bool = False
    independent_review_ref: str | None = None
    human_approval_ref: str | None = None
    canary_environment_ref: str | None = None


class CanaryImprovementDecision(BaseModel):
    contract: str = TRAJECTORY_IMPROVEMENT_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ImprovementStatus
    canary_activation_allowed: bool
    production_activation_allowed: bool = False
    automatic_self_modification_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def decision_never_promotes_directly_to_production(self) -> "CanaryImprovementDecision":
        if self.production_activation_allowed or self.automatic_self_modification_allowed:
            raise ValueError("trajectory_improvement_direct_production_activation_forbidden")
        if self.canary_activation_allowed:
            if self.status is not ImprovementStatus.APPROVED_FOR_CANARY or self.blockers:
                raise ValueError("canary_activation_requires_approved_unblocked_candidate")
        elif self.status is ImprovementStatus.APPROVED_FOR_CANARY:
            raise ValueError("approved_for_canary_must_allow_canary")
        return self


def _candidate_id(
    *,
    tenant_id: str,
    target: ImprovementTarget,
    revision_artifact_ref: str,
    trace_ids: tuple[str, ...],
    evaluation_refs: tuple[str, ...],
) -> str:
    canonical = json.dumps(
        {
            "contract": TRAJECTORY_IMPROVEMENT_CONTRACT,
            "tenant_id": tenant_id,
            "target": target.value,
            "revision_artifact_ref": revision_artifact_ref,
            "trace_ids": trace_ids,
            "evaluation_refs": evaluation_refs,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def propose_offline_improvement(
    *,
    evaluations: tuple[OfflineTrajectoryEvaluation, ...],
    target: ImprovementTarget,
    revision_artifact_ref: str,
) -> ImprovementCandidate:
    if not evaluations:
        raise ValueError("trajectory_improvement_requires_evaluation")
    if not revision_artifact_ref.strip():
        raise ValueError("trajectory_improvement_requires_revision_artifact_ref")
    tenant_ids = {item.tenant_id for item in evaluations}
    if len(tenant_ids) != 1:
        raise ValueError("trajectory_improvement_cross_tenant_evidence_forbidden")
    if any(item.ambiguous_side_effect_observed for item in evaluations) and target not in {
        ImprovementTarget.EFFECT_VERIFIER,
        ImprovementTarget.WORKFLOW_GRAPH,
    }:
        raise ValueError("ambiguous_side_effect_improvement_must_target_verifier_or_workflow")

    trace_ids = tuple(sorted({item.trace_id for item in evaluations}))
    evaluation_refs = tuple(sorted({item.evaluation_id for item in evaluations}))
    evidence_refs = tuple(
        dict.fromkeys(ref for item in evaluations for ref in item.evidence_refs)
    )
    tenant_id = next(iter(tenant_ids))
    return ImprovementCandidate(
        candidate_id=_candidate_id(
            tenant_id=tenant_id,
            target=target,
            revision_artifact_ref=revision_artifact_ref,
            trace_ids=trace_ids,
            evaluation_refs=evaluation_refs,
        ),
        tenant_id=tenant_id,
        target=target,
        revision_artifact_ref=revision_artifact_ref,
        source_trace_ids=trace_ids,
        evaluation_refs=evaluation_refs,
        evidence_refs=evidence_refs,
    )


def qualify_improvement_for_canary(
    *,
    candidate: ImprovementCandidate,
    validation: ImprovementValidationEvidence,
    minimum_samples: int = 20,
) -> CanaryImprovementDecision:
    if validation.candidate_id != candidate.candidate_id:
        raise ValueError("trajectory_validation_candidate_mismatch")
    if minimum_samples < 1:
        raise ValueError("trajectory_validation_minimum_samples_must_be_positive")

    blockers: list[str] = []
    if not validation.jarvisbench_passed or not validation.jarvisbench_evidence_ref:
        blockers.append("trajectory_improvement_jarvisbench_not_passed")
    if validation.minimum_sample_count < minimum_samples:
        blockers.append("trajectory_improvement_sample_count_insufficient")
    if not validation.no_safety_regression:
        blockers.append("trajectory_improvement_safety_regression_not_cleared")
    if not validation.independent_review_ref:
        blockers.append("trajectory_improvement_independent_review_missing")
    if not validation.human_approval_ref:
        blockers.append("trajectory_improvement_human_approval_missing")
    if not validation.canary_environment_ref:
        blockers.append("trajectory_improvement_canary_environment_missing")

    allowed = not blockers
    return CanaryImprovementDecision(
        candidate_id=candidate.candidate_id,
        status=(ImprovementStatus.APPROVED_FOR_CANARY if allowed else ImprovementStatus.BLOCKED),
        canary_activation_allowed=allowed,
        blockers=tuple(blockers),
    )
