"""Evidence-bound transfer and out-of-distribution generalization for Jarvis.

The novel-problem solver can prove that a solution is strong for one problem frame.
This layer asks a different question: does the selected mechanism preserve its
constraints and decision boundary under independently designed holdouts, domain
shift, temporal shift, adversarial perturbation and negative controls?

A READY artifact authorizes only a bounded transfer claim over the tested scope. It
never authorizes universal generalization, Company Truth promotion, provider use,
policy/model updates, execution, or side effects.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .novel_problem_solver_intelligence import (
    NovelProblemDisposition,
    NovelProblemSolutionArtifact,
)

TRANSFER_GENERALIZATION_CONTRACT = "eay-transfer-generalization-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TransferDisposition(str, Enum):
    READY = "ready"
    HOLD = "hold"


class TransferScenarioFamily(str, Enum):
    NEAR_DISTRIBUTION = "near_distribution"
    DOMAIN_SHIFT = "domain_shift"
    TEMPORAL_SHIFT = "temporal_shift"
    ADVERSARIAL_PERTURBATION = "adversarial_perturbation"
    NEGATIVE_CONTROL = "negative_control"


class TransferEvaluationOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


_REQUIRED_FAMILIES = frozenset(TransferScenarioFamily)


class TransferGeneralizationPolicy(SealedModel):
    minimum_scenarios: int = Field(default=5, ge=5, le=32)
    minimum_holdout_scenarios: int = Field(default=2, ge=1, le=16)
    minimum_independent_evaluators: int = Field(default=2, ge=2, le=8)
    minimum_conservative_score: float = Field(default=0.70, ge=0.0, le=1.0)
    minimum_ready_fraction: float = Field(default=1.0, ge=0.80, le=1.0)
    require_all_core_families: bool = True

    @model_validator(mode="after")
    def strict_core_families(self) -> "TransferGeneralizationPolicy":
        if not self.require_all_core_families:
            raise ValueError("transfer_generalization_core_families_cannot_be_disabled")
        return self


class TransferScenario(SealedModel):
    scenario_id: str = Field(pattern=_SCOPE)
    family: TransferScenarioFamily
    description: str = Field(min_length=8)
    expected_solution_applicable: bool
    changed_factors: tuple[str, ...] = Field(min_length=1)
    preserved_constraints: tuple[str, ...] = Field(min_length=1)
    challenged_assumptions: tuple[str, ...] = ()
    independently_designed: bool
    holdout: bool
    design_evidence_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_content(self) -> "TransferScenario":
        for code, values in (
            ("changed_factors", self.changed_factors),
            ("preserved_constraints", self.preserved_constraints),
            ("challenged_assumptions", self.challenged_assumptions),
            ("evidence_refs", self.evidence_refs),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"transfer_scenario_{code}_must_be_unique")
        if self.family is TransferScenarioFamily.NEGATIVE_CONTROL:
            if self.expected_solution_applicable:
                raise ValueError("transfer_negative_control_must_expect_non_application")
            if not self.challenged_assumptions:
                raise ValueError("transfer_negative_control_requires_challenged_assumption")
        return self


class IndependentTransferEvaluation(SealedModel):
    evaluation_id: str = Field(pattern=_SCOPE)
    scenario_id: str = Field(pattern=_SCOPE)
    evaluator_ref: str = Field(pattern=_SCOPE)
    independent_evaluator: bool
    outcome: TransferEvaluationOutcome
    boundary_respected: bool
    constraints_satisfied: bool
    mechanism_transfer: float = Field(ge=0.0, le=1.0)
    expected_outcome_alignment: float = Field(ge=0.0, le=1.0)
    robustness: float = Field(ge=0.0, le=1.0)
    calibration: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    unresolved_material_objections: int = Field(ge=0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_is_unique(self) -> "IndependentTransferEvaluation":
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("transfer_evaluation_evidence_refs_must_be_unique")
        return self

    @property
    def composite_score(self) -> float:
        return round(
            (
                self.mechanism_transfer
                + self.expected_outcome_alignment
                + self.robustness
                + self.calibration
                + self.evidence_strength
            )
            / 5.0,
            6,
        )


class TransferScenarioScore(SealedModel):
    scenario_id: str = Field(pattern=_SCOPE)
    family: TransferScenarioFamily
    conservative_score: float = Field(ge=0.0, le=1.0)
    independent_evaluator_count: int = Field(ge=0)
    eligible: bool
    blockers: tuple[str, ...] = ()


class TransferGeneralizationArtifact(SealedModel):
    contract: str = TRANSFER_GENERALIZATION_CONTRACT
    problem_id: str = Field(pattern=_SCOPE)
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    source_solution_artifact_fingerprint: str = Field(pattern=_DIGEST)
    selected_solution_id: str = Field(pattern=_SCOPE)
    tested_scope_families: tuple[TransferScenarioFamily, ...]
    scenario_count: int = Field(ge=0)
    holdout_scenario_count: int = Field(ge=0)
    ready_fraction: float = Field(ge=0.0, le=1.0)
    worst_case_score: float = Field(ge=0.0, le=1.0)
    generalizable_invariants: tuple[str, ...]
    context_bound_assumptions: tuple[str, ...]
    scenario_scores: tuple[TransferScenarioScore, ...]
    disposition: TransferDisposition
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    bounded_transfer_claim_allowed: bool
    universal_generalization_claim_allowed: bool = False
    company_truth_promoted: bool = False
    provider_authority_granted: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral_and_non_authoritative(self) -> "TransferGeneralizationArtifact":
        if any(
            (
                self.universal_generalization_claim_allowed,
                self.company_truth_promoted,
                self.provider_authority_granted,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("transfer_generalization_never_mints_authority_or_universal_claim")
        if self.disposition is TransferDisposition.READY:
            if self.blockers or not self.bounded_transfer_claim_allowed:
                raise ValueError("transfer_ready_requires_bounded_claim_without_blockers")
        elif self.bounded_transfer_claim_allowed:
            raise ValueError("transfer_hold_cannot_allow_bounded_claim")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("transfer_generalization_fingerprint_mismatch")
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


def _validate_source(
    *,
    source: NovelProblemSolutionArtifact,
    tenant_id: str,
    company_id: str,
    problem_id: str,
) -> NovelProblemSolutionArtifact:
    source = NovelProblemSolutionArtifact.model_validate(source.model_dump(mode="json"))
    if source.tenant_id != tenant_id:
        raise ValueError("transfer_cross_tenant_source_forbidden")
    if source.company_id != company_id:
        raise ValueError("transfer_cross_company_source_forbidden")
    if source.problem_id != problem_id:
        raise ValueError("transfer_problem_scope_mismatch")
    if source.disposition is not NovelProblemDisposition.READY:
        raise ValueError("transfer_requires_ready_novel_solution")
    if not source.selected_solution_id:
        raise ValueError("transfer_requires_selected_solution")
    return source


def _common_invariants(scenarios: tuple[TransferScenario, ...]) -> tuple[str, ...]:
    if not scenarios:
        return ()
    common = set(scenarios[0].preserved_constraints)
    for scenario in scenarios[1:]:
        common.intersection_update(scenario.preserved_constraints)
    return tuple(sorted(common))


def evaluate_transfer_generalization(
    *,
    source: NovelProblemSolutionArtifact,
    tenant_id: str,
    company_id: str,
    problem_id: str,
    scenarios: tuple[TransferScenario, ...],
    evaluations: tuple[IndependentTransferEvaluation, ...],
    policy: TransferGeneralizationPolicy | None = None,
) -> TransferGeneralizationArtifact:
    """Evaluate bounded transfer without turning generalization into authority."""

    source = _validate_source(
        source=source,
        tenant_id=tenant_id,
        company_id=company_id,
        problem_id=problem_id,
    )
    rules = policy or TransferGeneralizationPolicy()
    scenarios = tuple(TransferScenario.model_validate(item.model_dump(mode="json")) for item in scenarios)
    evaluations = tuple(
        IndependentTransferEvaluation.model_validate(item.model_dump(mode="json"))
        for item in evaluations
    )

    scenario_ids = [item.scenario_id for item in scenarios]
    evaluation_ids = [item.evaluation_id for item in evaluations]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("transfer_scenario_ids_must_be_unique")
    if len(evaluation_ids) != len(set(evaluation_ids)):
        raise ValueError("transfer_evaluation_ids_must_be_unique")
    known_scenarios = set(scenario_ids)
    if any(item.scenario_id not in known_scenarios for item in evaluations):
        raise ValueError("transfer_evaluation_references_unknown_scenario")

    global_blockers: list[str] = []
    if len(scenarios) < rules.minimum_scenarios:
        global_blockers.append("transfer_minimum_scenario_count_missing")
    holdout_count = sum(1 for item in scenarios if item.holdout)
    if holdout_count < rules.minimum_holdout_scenarios:
        global_blockers.append("transfer_holdout_scenario_quorum_missing")

    families = {item.family for item in scenarios}
    for family in sorted(_REQUIRED_FAMILIES - families, key=lambda item: item.value):
        global_blockers.append(f"transfer_required_scenario_family_missing:{family.value}")

    source_evidence = set(source.evidence_refs)
    scenario_scores: list[TransferScenarioScore] = []
    all_evidence: set[str] = set()
    for scenario in scenarios:
        all_evidence.add(scenario.design_evidence_ref)
        all_evidence.update(scenario.evidence_refs)
        blockers: list[str] = []
        if not scenario.independently_designed:
            blockers.append("transfer_scenario_independent_design_required")

        items = [item for item in evaluations if item.scenario_id == scenario.scenario_id]
        evaluator_refs = {
            item.evaluator_ref for item in items if item.independent_evaluator
        }
        independent = [item for item in items if item.independent_evaluator]
        if len(evaluator_refs) < rules.minimum_independent_evaluators:
            blockers.append("transfer_independent_evaluator_quorum_missing")

        fresh_evidence_found = False
        for item in independent:
            all_evidence.update(item.evidence_refs)
            if any(ref not in source_evidence for ref in item.evidence_refs):
                fresh_evidence_found = True
            if item.outcome is TransferEvaluationOutcome.FAILED:
                blockers.append("transfer_scenario_failed")
            elif item.outcome is TransferEvaluationOutcome.INCONCLUSIVE:
                blockers.append("transfer_scenario_inconclusive")
            if not item.boundary_respected:
                blockers.append("transfer_decision_boundary_violated")
            if not item.constraints_satisfied:
                blockers.append("transfer_constraint_integrity_failed")
            if item.unresolved_material_objections:
                blockers.append("transfer_material_objection_unresolved")

        if independent and not fresh_evidence_found:
            blockers.append("transfer_fresh_evidence_required")
        conservative_score = min(
            (item.composite_score for item in independent),
            default=0.0,
        )
        if conservative_score < rules.minimum_conservative_score:
            blockers.append("transfer_conservative_score_below_floor")

        unique_blockers = tuple(dict.fromkeys(blockers))
        scenario_scores.append(
            TransferScenarioScore(
                scenario_id=scenario.scenario_id,
                family=scenario.family,
                conservative_score=conservative_score,
                independent_evaluator_count=len(evaluator_refs),
                eligible=not unique_blockers,
                blockers=unique_blockers,
            )
        )

    ready_count = sum(1 for item in scenario_scores if item.eligible)
    ready_fraction = round(ready_count / len(scenarios), 6) if scenarios else 0.0
    if ready_fraction < rules.minimum_ready_fraction:
        global_blockers.append("transfer_ready_fraction_below_floor")
    if any(not item.eligible for item in scenario_scores):
        global_blockers.append("transfer_one_or_more_scenarios_not_generalized")

    worst_case_score = min(
        (item.conservative_score for item in scenario_scores),
        default=0.0,
    )
    context_bound_assumptions = tuple(
        sorted(
            {
                assumption
                for scenario in scenarios
                if not scenario.expected_solution_applicable
                for assumption in scenario.challenged_assumptions
            }
        )
    )
    blockers = tuple(dict.fromkeys(global_blockers))
    disposition = TransferDisposition.HOLD if blockers else TransferDisposition.READY
    values = {
        "contract": TRANSFER_GENERALIZATION_CONTRACT,
        "problem_id": problem_id,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "source_solution_artifact_fingerprint": source.fingerprint,
        "selected_solution_id": source.selected_solution_id,
        "tested_scope_families": tuple(sorted(families, key=lambda item: item.value)),
        "scenario_count": len(scenarios),
        "holdout_scenario_count": holdout_count,
        "ready_fraction": ready_fraction,
        "worst_case_score": worst_case_score,
        "generalizable_invariants": _common_invariants(scenarios),
        "context_bound_assumptions": context_bound_assumptions,
        "scenario_scores": tuple(scenario_scores),
        "disposition": disposition,
        "blockers": blockers,
        "evidence_refs": tuple(sorted(all_evidence)),
        "bounded_transfer_claim_allowed": disposition is TransferDisposition.READY,
        "universal_generalization_claim_allowed": False,
        "company_truth_promoted": False,
        "provider_authority_granted": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
    }
    draft = TransferGeneralizationArtifact.model_construct(
        **values,
        fingerprint="0" * 64,
    )
    return TransferGeneralizationArtifact(
        **values,
        fingerprint=_seal(_payload(draft)),
    )
