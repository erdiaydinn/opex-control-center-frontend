"""Counterfactual solution-tree authority for evidence-bound novel problem solving.

This layer composes the existing Autonomous Investigator and frontier deliberation
contracts. It does not invent a second research engine or provider gateway. A novel
problem may become decision-ready only after multiple materially distinct solution
roots are explored, selectable leaves survive counterfactual stress and independent
decisive falsification, constraints hold, and independent evaluators produce a
clear conservative margin. The result remains advisory and cannot execute anything.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .autonomous_investigator import (
    AutonomousInvestigationReport,
    InvestigatorDisposition,
    ProblemNovelty,
)
from .frontier_supremacy_intelligence import (
    EngineDomainBenchmark,
    SupremacyDomain,
    SupremacyRequest,
    SupremacyResult,
    execute_frontier_supremacy,
)
from .intelligence_router import IntelligenceTask

NOVEL_PROBLEM_SOLVING_CONTRACT = "eay-novel-problem-solving-v1"
NOVEL_PROBLEM_FRONTIER_CONTRACT = "eay-verified-novel-problem-frontier-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class NovelProblemDisposition(str, Enum):
    READY = "ready"
    HOLD = "hold"


class FalsificationOutcome(str, Enum):
    SURVIVED = "survived"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class NovelProblemPolicy(BaseModel):
    minimum_root_strategies: int = Field(default=3, ge=3, le=8)
    maximum_nodes: int = Field(default=24, ge=3, le=128)
    maximum_depth: int = Field(default=3, ge=1, le=8)
    minimum_counterfactuals_per_candidate: int = Field(default=1, ge=1, le=8)
    minimum_independent_falsifiers: int = Field(default=2, ge=1, le=8)
    minimum_independent_evaluators: int = Field(default=2, ge=1, le=8)
    minimum_conservative_score: float = Field(default=0.65, ge=0.0, le=1.0)
    minimum_decisive_margin: float = Field(default=0.05, ge=0.0, le=0.50)


class NovelProblemFrame(BaseModel):
    contract: str = NOVEL_PROBLEM_SOLVING_CONTRACT
    problem_id: str = Field(pattern=_SCOPE)
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    objective: str = Field(min_length=8)
    constraints: tuple[str, ...] = Field(min_length=1)
    investigation_fingerprint: str = Field(pattern=_DIGEST)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    policy: NovelProblemPolicy = Field(default_factory=NovelProblemPolicy)

    @model_validator(mode="after")
    def frame_is_unique(self) -> "NovelProblemFrame":
        if len(self.constraints) != len(set(self.constraints)):
            raise ValueError("novel_problem_constraints_must_be_unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("novel_problem_frame_evidence_refs_must_be_unique")
        return self


class SolutionNode(BaseModel):
    solution_id: str = Field(pattern=_SCOPE)
    parent_solution_id: str | None = Field(default=None, pattern=_SCOPE)
    strategy_key: str = Field(pattern=_SCOPE)
    proposal: str = Field(min_length=8)
    mechanism: str = Field(min_length=8)
    assumptions: tuple[str, ...] = Field(min_length=1)
    predicted_outcomes: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    selectable: bool = True

    @model_validator(mode="after")
    def solution_content_is_unique(self) -> "SolutionNode":
        if self.parent_solution_id == self.solution_id:
            raise ValueError("novel_solution_cannot_parent_itself")
        if len(self.assumptions) != len(set(self.assumptions)):
            raise ValueError("novel_solution_assumptions_must_be_unique")
        if len(self.predicted_outcomes) != len(set(self.predicted_outcomes)):
            raise ValueError("novel_solution_predictions_must_be_unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("novel_solution_evidence_refs_must_be_unique")
        return self


class CounterfactualStressTest(BaseModel):
    counterfactual_id: str = Field(pattern=_SCOPE)
    solution_id: str = Field(pattern=_SCOPE)
    changed_assumption: str = Field(min_length=3)
    alternative_condition: str = Field(min_length=3)
    predicted_effect: str = Field(min_length=3)
    failure_boundary: str = Field(min_length=3)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class DecisiveFalsificationProbe(BaseModel):
    probe_id: str = Field(pattern=_SCOPE)
    solution_id: str = Field(pattern=_SCOPE)
    falsifier_ref: str = Field(pattern=_SCOPE)
    independent_evaluator: bool
    decisive_test: str = Field(min_length=8)
    outcome: FalsificationOutcome
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class IndependentSolutionEvaluation(BaseModel):
    evaluation_id: str = Field(pattern=_SCOPE)
    solution_id: str = Field(pattern=_SCOPE)
    evaluator_ref: str = Field(pattern=_SCOPE)
    independent_evaluator: bool
    constraints_satisfied: bool
    feasibility: float = Field(ge=0.0, le=1.0)
    expected_impact: float = Field(ge=0.0, le=1.0)
    robustness: float = Field(ge=0.0, le=1.0)
    reversibility: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    unresolved_material_objections: int = Field(ge=0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @property
    def composite_score(self) -> float:
        return round(
            (
                self.feasibility
                + self.expected_impact
                + self.robustness
                + self.reversibility
                + self.evidence_strength
            )
            / 5.0,
            6,
        )


class NovelCandidateScore(BaseModel):
    solution_id: str
    root_strategy_key: str
    conservative_score: float = Field(ge=0.0, le=1.0)
    evaluator_count: int = Field(ge=0)
    survived_falsifier_count: int = Field(ge=0)
    counterfactual_count: int = Field(ge=0)
    eligible: bool
    blockers: tuple[str, ...] = ()


class NovelProblemSolutionArtifact(BaseModel):
    contract: str = NOVEL_PROBLEM_SOLVING_CONTRACT
    problem_id: str
    tenant_id: str
    company_id: str
    investigation_fingerprint: str = Field(pattern=_DIGEST)
    solution_ids: tuple[str, ...]
    root_strategy_keys: tuple[str, ...]
    candidate_scores: tuple[NovelCandidateScore, ...]
    selected_solution_id: str | None = None
    decisive_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    disposition: NovelProblemDisposition
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    execution_authority_granted: bool = False
    company_truth_promoted: bool = False
    automatic_action_allowed: bool = False
    superiority_claim_allowed: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def artifact_is_integral_and_non_authoritative(self) -> "NovelProblemSolutionArtifact":
        if any(
            (
                self.execution_authority_granted,
                self.company_truth_promoted,
                self.automatic_action_allowed,
                self.superiority_claim_allowed,
            )
        ):
            raise ValueError("novel_problem_solution_never_mints_authority_or_claim")
        if self.disposition is NovelProblemDisposition.READY:
            if self.blockers or not self.selected_solution_id:
                raise ValueError("novel_problem_ready_requires_selected_solution_without_blockers")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != _seal(payload):
            raise ValueError("novel_problem_solution_fingerprint_mismatch")
        return self


class VerifiedNovelFrontierRequest(BaseModel):
    contract: str = NOVEL_PROBLEM_FRONTIER_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    problem: str = Field(min_length=8)
    task: IntelligenceTask
    benchmarks: tuple[EngineDomainBenchmark, ...] = Field(min_length=1)
    solution_artifact: NovelProblemSolutionArtifact

    @model_validator(mode="after")
    def ready_and_scoped(self) -> "VerifiedNovelFrontierRequest":
        if self.solution_artifact.tenant_id != self.tenant_id:
            raise ValueError("novel_frontier_cross_tenant_artifact_forbidden")
        if self.solution_artifact.company_id != self.company_id:
            raise ValueError("novel_frontier_cross_company_artifact_forbidden")
        if self.solution_artifact.disposition is not NovelProblemDisposition.READY:
            raise ValueError("novel_frontier_solution_artifact_not_ready")
        return self


class VerifiedNovelFrontierResult(BaseModel):
    contract: str = NOVEL_PROBLEM_FRONTIER_CONTRACT
    tenant_id: str
    company_id: str
    solution_artifact_fingerprint: str = Field(pattern=_DIGEST)
    supremacy: SupremacyResult
    execution_authority_granted: bool = False
    company_truth_promoted: bool = False
    superiority_claim_allowed: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def sealed_result(self) -> "VerifiedNovelFrontierResult":
        if self.execution_authority_granted or self.company_truth_promoted or self.superiority_claim_allowed:
            raise ValueError("novel_frontier_result_never_mints_authority_or_claim")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != _seal(payload):
            raise ValueError("novel_frontier_result_fingerprint_mismatch")
        return self


class NovelFrontierGateway(Protocol):
    def plan(self, task: IntelligenceTask): ...

    async def invoke_primary(self, *, task: IntelligenceTask, prompt: str): ...

    async def invoke_routed_engines(self, *, task: IntelligenceTask, prompt: str): ...


def _seal(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_investigation(
    frame: NovelProblemFrame,
    investigation: AutonomousInvestigationReport,
) -> None:
    investigation = AutonomousInvestigationReport.model_validate(
        investigation.model_dump(mode="json")
    )
    if investigation.problem_id != frame.problem_id:
        raise ValueError("novel_problem_investigation_problem_mismatch")
    if investigation.tenant_id != frame.tenant_id:
        raise ValueError("novel_problem_investigation_tenant_mismatch")
    if investigation.company_id != frame.company_id:
        raise ValueError("novel_problem_investigation_company_mismatch")
    if investigation.fingerprint != frame.investigation_fingerprint:
        raise ValueError("novel_problem_investigation_fingerprint_mismatch")
    if investigation.novelty is not ProblemNovelty.NOVEL:
        raise ValueError("novel_problem_requires_novel_investigation")
    if investigation.disposition is not InvestigatorDisposition.DECISION_READY:
        raise ValueError("novel_problem_investigation_not_decision_ready")


def _tree_metadata(
    nodes: tuple[SolutionNode, ...], policy: NovelProblemPolicy
) -> tuple[dict[str, SolutionNode], dict[str, str], dict[str, int], set[str]]:
    if len(nodes) > policy.maximum_nodes:
        raise ValueError("novel_solution_tree_node_budget_exceeded")
    ids = [node.solution_id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("novel_solution_ids_must_be_unique")
    by_id = {node.solution_id: node for node in nodes}
    children: dict[str, set[str]] = {node.solution_id: set() for node in nodes}
    for node in nodes:
        if node.parent_solution_id:
            if node.parent_solution_id not in by_id:
                raise ValueError("novel_solution_tree_orphan_node")
            children[node.parent_solution_id].add(node.solution_id)

    root_for: dict[str, str] = {}
    depth_for: dict[str, int] = {}
    for node in nodes:
        seen: set[str] = set()
        current = node
        depth = 0
        while current.parent_solution_id is not None:
            if current.solution_id in seen:
                raise ValueError("novel_solution_tree_cycle_detected")
            seen.add(current.solution_id)
            depth += 1
            if depth > policy.maximum_depth:
                raise ValueError("novel_solution_tree_depth_budget_exceeded")
            current = by_id[current.parent_solution_id]
        root_for[node.solution_id] = current.solution_id
        depth_for[node.solution_id] = depth

    roots = {node.solution_id for node in nodes if node.parent_solution_id is None}
    root_strategies = [by_id[root].strategy_key for root in roots]
    if len(roots) < policy.minimum_root_strategies:
        raise ValueError("novel_solution_minimum_root_strategies_missing")
    if len(root_strategies) != len(set(root_strategies)):
        raise ValueError("novel_solution_root_strategies_must_be_distinct")

    selectable = {node.solution_id for node in nodes if node.selectable}
    if any(children[node_id] for node_id in selectable):
        raise ValueError("novel_solution_selectable_candidate_must_be_leaf")
    represented_roots = {root_for[node_id] for node_id in selectable}
    if len(represented_roots) < policy.minimum_root_strategies:
        raise ValueError("novel_solution_selectable_candidates_must_cover_root_strategies")
    return by_id, root_for, depth_for, selectable


def evaluate_novel_solution_tree(
    *,
    frame: NovelProblemFrame,
    investigation: AutonomousInvestigationReport,
    solutions: tuple[SolutionNode, ...],
    counterfactuals: tuple[CounterfactualStressTest, ...],
    falsification_probes: tuple[DecisiveFalsificationProbe, ...],
    evaluations: tuple[IndependentSolutionEvaluation, ...],
) -> NovelProblemSolutionArtifact:
    frame = NovelProblemFrame.model_validate(frame.model_dump(mode="json"))
    _validate_investigation(frame, investigation)
    by_id, root_for, _, selectable = _tree_metadata(solutions, frame.policy)

    counterfactual_ids = [item.counterfactual_id for item in counterfactuals]
    probe_ids = [item.probe_id for item in falsification_probes]
    evaluation_ids = [item.evaluation_id for item in evaluations]
    if len(counterfactual_ids) != len(set(counterfactual_ids)):
        raise ValueError("novel_counterfactual_ids_must_be_unique")
    if len(probe_ids) != len(set(probe_ids)):
        raise ValueError("novel_falsification_probe_ids_must_be_unique")
    if len(evaluation_ids) != len(set(evaluation_ids)):
        raise ValueError("novel_solution_evaluation_ids_must_be_unique")

    known = set(by_id)
    if any(item.solution_id not in known for item in counterfactuals):
        raise ValueError("novel_counterfactual_unknown_solution")
    if any(item.solution_id not in known for item in falsification_probes):
        raise ValueError("novel_falsification_unknown_solution")
    if any(item.solution_id not in known for item in evaluations):
        raise ValueError("novel_evaluation_unknown_solution")

    scores: list[NovelCandidateScore] = []
    global_blockers: list[str] = []
    evidence_refs: list[str] = list(frame.evidence_refs)
    for node in solutions:
        evidence_refs.extend(node.evidence_refs)

    for solution_id in sorted(selectable):
        blockers: list[str] = []
        cf = [item for item in counterfactuals if item.solution_id == solution_id]
        probes = [item for item in falsification_probes if item.solution_id == solution_id]
        reviews = [item for item in evaluations if item.solution_id == solution_id]
        for item in cf:
            evidence_refs.extend(item.evidence_refs)
        for item in probes:
            evidence_refs.extend(item.evidence_refs)
        for item in reviews:
            evidence_refs.extend(item.evidence_refs)

        if len(cf) < frame.policy.minimum_counterfactuals_per_candidate:
            blockers.append("novel_candidate_counterfactual_missing")

        independent_probes = [item for item in probes if item.independent_evaluator]
        falsifier_refs = {item.falsifier_ref for item in independent_probes}
        if len(falsifier_refs) < frame.policy.minimum_independent_falsifiers:
            blockers.append("novel_candidate_independent_falsifier_quorum_missing")
        if any(item.outcome is FalsificationOutcome.REFUTED for item in probes):
            blockers.append("novel_candidate_refuted")
        if any(item.outcome is FalsificationOutcome.INCONCLUSIVE for item in independent_probes):
            blockers.append("novel_candidate_decisive_falsification_inconclusive")
        survived_refs = {
            item.falsifier_ref
            for item in independent_probes
            if item.outcome is FalsificationOutcome.SURVIVED
        }
        if len(survived_refs) < frame.policy.minimum_independent_falsifiers:
            blockers.append("novel_candidate_survived_falsifier_quorum_missing")

        independent_reviews = [item for item in reviews if item.independent_evaluator]
        evaluator_refs = {item.evaluator_ref for item in independent_reviews}
        if len(evaluator_refs) < frame.policy.minimum_independent_evaluators:
            blockers.append("novel_candidate_independent_evaluator_quorum_missing")
        if any(not item.constraints_satisfied for item in reviews):
            blockers.append("novel_candidate_constraint_violation")
        if any(item.unresolved_material_objections for item in reviews):
            blockers.append("novel_candidate_material_objection_unresolved")

        conservative = (
            min(item.composite_score for item in independent_reviews)
            if independent_reviews
            else 0.0
        )
        if conservative < frame.policy.minimum_conservative_score:
            blockers.append("novel_candidate_conservative_score_below_floor")
        root_id = root_for[solution_id]
        scores.append(
            NovelCandidateScore(
                solution_id=solution_id,
                root_strategy_key=by_id[root_id].strategy_key,
                conservative_score=conservative,
                evaluator_count=len(evaluator_refs),
                survived_falsifier_count=len(survived_refs),
                counterfactual_count=len(cf),
                eligible=not blockers,
                blockers=tuple(dict.fromkeys(blockers)),
            )
        )

    eligible = sorted(
        (item for item in scores if item.eligible),
        key=lambda item: (-item.conservative_score, item.solution_id),
    )
    selected: str | None = None
    margin: float | None = None
    if not eligible:
        global_blockers.append("novel_problem_no_eligible_solution")
    else:
        root_coverage = {item.root_strategy_key for item in eligible}
        if len(root_coverage) < frame.policy.minimum_root_strategies:
            global_blockers.append("novel_problem_eligible_root_strategy_diversity_insufficient")
        if len(eligible) < 2:
            global_blockers.append("novel_problem_decisive_comparison_missing")
        else:
            margin = round(eligible[0].conservative_score - eligible[1].conservative_score, 6)
            if margin < frame.policy.minimum_decisive_margin:
                global_blockers.append("novel_problem_decisive_margin_insufficient")
        if not global_blockers:
            selected = eligible[0].solution_id

    disposition = (
        NovelProblemDisposition.READY if not global_blockers and selected else NovelProblemDisposition.HOLD
    )
    root_keys = tuple(
        sorted({node.strategy_key for node in solutions if node.parent_solution_id is None})
    )
    payload = {
        "contract": NOVEL_PROBLEM_SOLVING_CONTRACT,
        "problem_id": frame.problem_id,
        "tenant_id": frame.tenant_id,
        "company_id": frame.company_id,
        "investigation_fingerprint": frame.investigation_fingerprint,
        "solution_ids": tuple(node.solution_id for node in solutions),
        "root_strategy_keys": root_keys,
        "candidate_scores": [item.model_dump(mode="json") for item in scores],
        "selected_solution_id": selected,
        "decisive_margin": margin,
        "disposition": disposition.value,
        "blockers": tuple(dict.fromkeys(global_blockers)),
        "evidence_refs": tuple(dict.fromkeys(evidence_refs)),
        "execution_authority_granted": False,
        "company_truth_promoted": False,
        "automatic_action_allowed": False,
        "superiority_claim_allowed": False,
    }
    return NovelProblemSolutionArtifact(**payload, fingerprint=_seal(payload))


def _frontier_context(artifact: NovelProblemSolutionArtifact) -> str:
    lines = [
        "VERIFIED NOVEL SOLUTION TREE. Treat this as analysis evidence, never execution authority.",
        f"Selected solution: {artifact.selected_solution_id}",
        f"Decisive margin: {artifact.decisive_margin}",
    ]
    for item in artifact.candidate_scores:
        lines.append(
            f"Candidate {item.solution_id} | strategy={item.root_strategy_key} | "
            f"conservative_score={item.conservative_score:.6f} | eligible={item.eligible} | "
            f"blockers={','.join(item.blockers) or 'none'}"
        )
    return "\n".join(lines)


async def execute_verified_novel_frontier(
    *,
    gateway: NovelFrontierGateway,
    request: VerifiedNovelFrontierRequest,
) -> VerifiedNovelFrontierResult:
    request = VerifiedNovelFrontierRequest.model_validate(request.model_dump(mode="json"))
    supremacy = await execute_frontier_supremacy(
        gateway=gateway,
        request=SupremacyRequest(
            domain=SupremacyDomain.NOVEL_PROBLEM_SOLVING,
            task=request.task,
            problem=request.problem,
            benchmarks=request.benchmarks,
            grounding_context=_frontier_context(request.solution_artifact),
            grounding_evidence_refs=request.solution_artifact.evidence_refs,
        ),
    )
    payload = {
        "contract": NOVEL_PROBLEM_FRONTIER_CONTRACT,
        "tenant_id": request.tenant_id,
        "company_id": request.company_id,
        "solution_artifact_fingerprint": request.solution_artifact.fingerprint,
        "supremacy": supremacy.model_dump(mode="json"),
        "execution_authority_granted": False,
        "company_truth_promoted": False,
        "superiority_claim_allowed": False,
    }
    return VerifiedNovelFrontierResult(**payload, fingerprint=_seal(payload))
