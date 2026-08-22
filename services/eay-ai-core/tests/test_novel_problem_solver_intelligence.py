from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.autonomous_investigator import (
    AutonomousInvestigationReport,
    InvestigatorDisposition,
    ProblemNovelty,
)
from app.frontier_supremacy_intelligence import EngineDomainBenchmark, SupremacyDomain
from app.intelligence_router import (
    IntelligenceRoutingPlan,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.novel_problem_solver_intelligence import (
    CounterfactualStressTest,
    DecisiveFalsificationProbe,
    FalsificationOutcome,
    IndependentSolutionEvaluation,
    NovelProblemDisposition,
    NovelProblemFrame,
    NovelProblemPolicy,
    NovelProblemSolutionArtifact,
    SolutionNode,
    VerifiedNovelFrontierRequest,
    evaluate_novel_solution_tree,
    execute_verified_novel_frontier,
)

NOW = datetime(2026, 8, 22, 1, 0, tzinfo=UTC)
TENANT = "tenant-a"
COMPANY = "company-a"
PROBLEM = "novel-problem-1"


def _seal(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def investigation(
    *,
    tenant: str = TENANT,
    company: str = COMPANY,
    problem_id: str = PROBLEM,
    disposition: InvestigatorDisposition = InvestigatorDisposition.DECISION_READY,
    novelty: ProblemNovelty = ProblemNovelty.NOVEL,
) -> AutonomousInvestigationReport:
    payload = {
        "contract": "eay-autonomous-investigator-v1",
        "problem_id": problem_id,
        "tenant_id": tenant,
        "company_id": company,
        "world_snapshot_fingerprint": "a" * 64,
        "novelty": novelty.value,
        "disposition": disposition.value,
        "ranking": None,
        "research_states": [],
        "next_research_tasks": [],
        "blockers": [] if disposition is InvestigatorDisposition.DECISION_READY else ["research_more"],
        "calibrated_confidence_cap": 0.86,
        "firm_company_claim_authorized": False,
        "execution_authority_granted": False,
        "production_truth_promoted": False,
    }
    return AutonomousInvestigationReport(**payload, fingerprint=_seal(payload))


def frame(report: AutonomousInvestigationReport | None = None, **overrides) -> NovelProblemFrame:
    report = report or investigation()
    values = dict(
        problem_id=PROBLEM,
        tenant_id=TENANT,
        company_id=COMPANY,
        objective="Design the strongest reversible solution for a novel operating problem",
        constraints=("Preserve tenant isolation", "No unauthorized side effects"),
        investigation_fingerprint=report.fingerprint,
        evidence_refs=("investigation://novel-problem-1",),
        policy=NovelProblemPolicy(),
    )
    values.update(overrides)
    return NovelProblemFrame(**values)


def solutions() -> tuple[SolutionNode, ...]:
    return (
        SolutionNode(
            solution_id="solution-a",
            strategy_key="architecture-first",
            proposal="Use a reversible architecture-first intervention",
            mechanism="Isolate the failure mode behind a bounded control layer",
            assumptions=("The control boundary is enforceable",),
            predicted_outcomes=("Failure propagation falls materially",),
            evidence_refs=("solution://a",),
        ),
        SolutionNode(
            solution_id="solution-b",
            strategy_key="process-first",
            proposal="Use an operational process-first intervention",
            mechanism="Change the workflow sequence and verification gates",
            assumptions=("Workflow sequencing drives the failure",),
            predicted_outcomes=("Operational error rate falls",),
            evidence_refs=("solution://b",),
        ),
        SolutionNode(
            solution_id="solution-c",
            strategy_key="data-first",
            proposal="Use an evidence and data-first intervention",
            mechanism="Improve observation quality before changing the control policy",
            assumptions=("Bad state estimation is a major contributor",),
            predicted_outcomes=("Decision quality improves without added authority",),
            evidence_refs=("solution://c",),
        ),
    )


def counterfactuals(
    omit: str | None = None,
) -> tuple[CounterfactualStressTest, ...]:
    items = []
    for suffix in ("a", "b", "c"):
        solution_id = f"solution-{suffix}"
        if solution_id == omit:
            continue
        items.append(
            CounterfactualStressTest(
                counterfactual_id=f"cf-{suffix}",
                solution_id=solution_id,
                changed_assumption=f"Reverse the critical assumption for {solution_id}",
                alternative_condition="Assume the suspected mechanism is not causal",
                predicted_effect="Expected benefit should materially weaken",
                failure_boundary="Reject the solution if benefit survives only by adding hidden assumptions",
                evidence_refs=(f"counterfactual://{suffix}",),
            )
        )
    return tuple(items)


def probes(
    *,
    refuted: str | None = None,
    inconclusive: str | None = None,
    single_falsifier: str | None = None,
) -> tuple[DecisiveFalsificationProbe, ...]:
    items = []
    for suffix in ("a", "b", "c"):
        solution_id = f"solution-{suffix}"
        refs = ("falsifier-one",) if solution_id == single_falsifier else ("falsifier-one", "falsifier-two")
        for index, falsifier_ref in enumerate(refs, start=1):
            outcome = FalsificationOutcome.SURVIVED
            if solution_id == refuted and index == 1:
                outcome = FalsificationOutcome.REFUTED
            if solution_id == inconclusive and index == 1:
                outcome = FalsificationOutcome.INCONCLUSIVE
            items.append(
                DecisiveFalsificationProbe(
                    probe_id=f"probe-{suffix}-{index}",
                    solution_id=solution_id,
                    falsifier_ref=falsifier_ref,
                    independent_evaluator=True,
                    decisive_test=f"Attempt to produce a decisive counterexample for {solution_id}",
                    outcome=outcome,
                    evidence_refs=(f"falsification://{suffix}/{index}",),
                )
            )
    return tuple(items)


def evaluations(
    *,
    scores: dict[str, float] | None = None,
    constraint_failure: str | None = None,
    unresolved: str | None = None,
    non_independent: str | None = None,
) -> tuple[IndependentSolutionEvaluation, ...]:
    score_map = scores or {"solution-a": 0.90, "solution-b": 0.76, "solution-c": 0.70}
    items = []
    for suffix in ("a", "b", "c"):
        solution_id = f"solution-{suffix}"
        base = score_map[solution_id]
        for index, evaluator_ref in enumerate(("reviewer-one", "reviewer-two"), start=1):
            score = max(0.0, base - (index - 1) * 0.01)
            items.append(
                IndependentSolutionEvaluation(
                    evaluation_id=f"evaluation-{suffix}-{index}",
                    solution_id=solution_id,
                    evaluator_ref=evaluator_ref,
                    independent_evaluator=not (
                        solution_id == non_independent and index == 2
                    ),
                    constraints_satisfied=solution_id != constraint_failure,
                    feasibility=score,
                    expected_impact=score,
                    robustness=score,
                    reversibility=score,
                    evidence_strength=score,
                    unresolved_material_objections=1 if solution_id == unresolved and index == 1 else 0,
                    evidence_refs=(f"evaluation://{suffix}/{index}",),
                )
            )
    return tuple(items)


def evaluate(**overrides) -> NovelProblemSolutionArtifact:
    report = overrides.pop("investigation", investigation())
    values = dict(
        frame=frame(report),
        investigation=report,
        solutions=solutions(),
        counterfactuals=counterfactuals(),
        falsification_probes=probes(),
        evaluations=evaluations(),
    )
    values.update(overrides)
    return evaluate_novel_solution_tree(**values)


def test_three_distinct_strategies_counterfactuals_falsifiers_and_evaluators_select_conservatively() -> None:
    result = evaluate()
    assert result.disposition is NovelProblemDisposition.READY
    assert result.selected_solution_id == "solution-a"
    assert result.decisive_margin == pytest.approx(0.14)
    assert result.blockers == ()
    assert len(result.root_strategy_keys) == 3
    assert all(item.evaluator_count == 2 for item in result.candidate_scores)
    assert all(item.survived_falsifier_count == 2 for item in result.candidate_scores)
    assert all(item.counterfactual_count == 1 for item in result.candidate_scores)
    assert result.execution_authority_granted is False
    assert result.company_truth_promoted is False
    assert result.automatic_action_allowed is False
    assert result.superiority_claim_allowed is False


def test_missing_counterfactual_makes_candidate_ineligible_and_breaks_strategy_diversity() -> None:
    result = evaluate(counterfactuals=counterfactuals(omit="solution-c"))
    assert result.disposition is NovelProblemDisposition.HOLD
    candidate = next(item for item in result.candidate_scores if item.solution_id == "solution-c")
    assert "novel_candidate_counterfactual_missing" in candidate.blockers
    assert "novel_problem_eligible_root_strategy_diversity_insufficient" in result.blockers


def test_refuted_or_inconclusive_candidate_cannot_survive_decisive_falsification() -> None:
    refuted = evaluate(falsification_probes=probes(refuted="solution-a"))
    candidate = next(item for item in refuted.candidate_scores if item.solution_id == "solution-a")
    assert candidate.eligible is False
    assert "novel_candidate_refuted" in candidate.blockers

    inconclusive = evaluate(falsification_probes=probes(inconclusive="solution-a"))
    candidate = next(item for item in inconclusive.candidate_scores if item.solution_id == "solution-a")
    assert candidate.eligible is False
    assert "novel_candidate_decisive_falsification_inconclusive" in candidate.blockers


def test_two_independent_decisive_falsifiers_are_required() -> None:
    result = evaluate(falsification_probes=probes(single_falsifier="solution-b"))
    candidate = next(item for item in result.candidate_scores if item.solution_id == "solution-b")
    assert candidate.eligible is False
    assert "novel_candidate_independent_falsifier_quorum_missing" in candidate.blockers
    assert "novel_candidate_survived_falsifier_quorum_missing" in candidate.blockers


def test_constraint_failure_unresolved_objection_and_non_independent_review_fail_closed() -> None:
    constrained = evaluate(evaluations=evaluations(constraint_failure="solution-a"))
    candidate = next(item for item in constrained.candidate_scores if item.solution_id == "solution-a")
    assert "novel_candidate_constraint_violation" in candidate.blockers

    unresolved = evaluate(evaluations=evaluations(unresolved="solution-a"))
    candidate = next(item for item in unresolved.candidate_scores if item.solution_id == "solution-a")
    assert "novel_candidate_material_objection_unresolved" in candidate.blockers

    non_independent = evaluate(evaluations=evaluations(non_independent="solution-a"))
    candidate = next(item for item in non_independent.candidate_scores if item.solution_id == "solution-a")
    assert "novel_candidate_independent_evaluator_quorum_missing" in candidate.blockers


def test_close_scores_force_hold_instead_of_false_decisiveness() -> None:
    result = evaluate(
        evaluations=evaluations(
            scores={"solution-a": 0.80, "solution-b": 0.78, "solution-c": 0.70}
        )
    )
    assert result.disposition is NovelProblemDisposition.HOLD
    assert result.selected_solution_id is None
    assert result.decisive_margin == pytest.approx(0.02)
    assert "novel_problem_decisive_margin_insufficient" in result.blockers


def test_low_conservative_worst_case_score_rejects_candidate() -> None:
    result = evaluate(
        evaluations=evaluations(
            scores={"solution-a": 0.90, "solution-b": 0.76, "solution-c": 0.60}
        )
    )
    candidate = next(item for item in result.candidate_scores if item.solution_id == "solution-c")
    assert candidate.eligible is False
    assert "novel_candidate_conservative_score_below_floor" in candidate.blockers


def test_tree_rejects_duplicate_roots_orphans_cycles_and_selectable_non_leaves() -> None:
    duplicate_strategy = list(solutions())
    duplicate_strategy[2] = duplicate_strategy[2].model_copy(update={"strategy_key": "architecture-first"})
    with pytest.raises(ValueError, match="novel_solution_root_strategies_must_be_distinct"):
        evaluate(solutions=tuple(duplicate_strategy))

    orphan = list(solutions())
    orphan[2] = orphan[2].model_copy(update={"parent_solution_id": "missing-parent"})
    with pytest.raises(ValueError, match="novel_solution_tree_orphan_node"):
        evaluate(solutions=tuple(orphan))

    cycle_nodes = (
        solutions()[0].model_copy(update={"parent_solution_id": "solution-b"}),
        solutions()[1].model_copy(update={"parent_solution_id": "solution-a"}),
        solutions()[2],
        SolutionNode(
            solution_id="solution-d",
            strategy_key="fourth-root",
            proposal="Provide a fourth independent root solution",
            mechanism="Use a distinct mechanism for cycle validation",
            assumptions=("Fourth root remains independent",),
            predicted_outcomes=("Cycle validator is exercised",),
            evidence_refs=("solution://d",),
        ),
        SolutionNode(
            solution_id="solution-e",
            strategy_key="fifth-root",
            proposal="Provide a fifth independent root solution",
            mechanism="Use another distinct mechanism for cycle validation",
            assumptions=("Fifth root remains independent",),
            predicted_outcomes=("Cycle validator still has enough roots",),
            evidence_refs=("solution://e",),
        ),
    )
    with pytest.raises(ValueError, match="novel_solution_tree_cycle_detected"):
        evaluate(solutions=cycle_nodes)

    roots = list(solutions())
    roots.append(
        SolutionNode(
            solution_id="solution-a-refined",
            parent_solution_id="solution-a",
            strategy_key="architecture-refinement",
            proposal="Refine architecture solution after new evidence",
            mechanism="Narrow the boundary while preserving reversibility",
            assumptions=("Refinement remains bounded",),
            predicted_outcomes=("Risk falls further",),
            evidence_refs=("solution://a/refined",),
        )
    )
    with pytest.raises(ValueError, match="novel_solution_selectable_candidate_must_be_leaf"):
        evaluate(solutions=tuple(roots))


def test_investigation_scope_novelty_and_decision_readiness_are_authoritative_inputs() -> None:
    wrong_company = investigation(company="company-b")
    with pytest.raises(ValueError, match="novel_problem_investigation_company_mismatch"):
        evaluate(investigation=wrong_company, frame=frame(wrong_company, company_id=COMPANY))

    not_ready = investigation(disposition=InvestigatorDisposition.HOLD)
    with pytest.raises(ValueError, match="novel_problem_investigation_not_decision_ready"):
        evaluate(investigation=not_ready, frame=frame(not_ready))

    familiar = investigation(novelty=ProblemNovelty.FAMILIAR)
    with pytest.raises(ValueError, match="novel_problem_requires_novel_investigation"):
        evaluate(investigation=familiar, frame=frame(familiar))


def test_solution_artifact_is_tamper_evident_and_deterministic() -> None:
    one = evaluate()
    two = evaluate()
    assert one.fingerprint == two.fingerprint
    raw = one.model_dump(mode="json")
    raw["selected_solution_id"] = "solution-b"
    with pytest.raises(ValidationError, match="novel_problem_solution_fingerprint_mismatch"):
        NovelProblemSolutionArtifact.model_validate(raw)


@dataclass
class Receipt:
    engine_id: str
    output_text: str


class FakeGateway:
    def plan(self, task: IntelligenceTask) -> IntelligenceRoutingPlan:
        return IntelligenceRoutingPlan(
            task_id=task.task_id,
            primary_engine_id="sol",
            critic_engine_ids=("claude", "gemini"),
            council_required=True,
            execution_permitted=True,
        )

    async def invoke_primary(self, *, task: IntelligenceTask, prompt: str) -> Receipt:
        if "SYNTHESIZER" in prompt:
            return Receipt("sol", "Novel solution synthesis after counterfactual review")
        return Receipt("sol", "Independent novel solution analysis")

    async def invoke_routed_engines(
        self, *, task: IntelligenceTask, prompt: str
    ) -> tuple[Receipt, ...]:
        if "FINAL VERIFIER" in prompt:
            return (
                Receipt("sol", "primary ignored"),
                Receipt("claude", "VERDICT: PASS\nCounterfactual boundary holds."),
                Receipt("gemini", "VERDICT: PASS\nNo decisive counterexample remains."),
            )
        return (
            Receipt("sol", "primary ignored"),
            Receipt("claude", "Independent critique of selected solution"),
            Receipt("gemini", "Independent falsification of selected solution"),
        )


def frontier_task() -> IntelligenceTask:
    return IntelligenceTask(
        task_id="novel-frontier-task",
        complexity=TaskComplexity.EXTREME,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
        requires_long_horizon=True,
        requires_independent_critique=True,
    )


def benchmarks() -> tuple[EngineDomainBenchmark, ...]:
    return tuple(
        EngineDomainBenchmark(
            engine_id=engine_id,
            provider_key=provider,
            domain=SupremacyDomain.NOVEL_PROBLEM_SOLVING,
            normalized_frontier_score=1.0,
            sample_count=250,
            measured_at=NOW,
            evidence_ref=f"benchmark://novel/{engine_id}",
            independent_evaluator=True,
        )
        for engine_id, provider in (
            ("sol", "openai"),
            ("claude", "anthropic"),
            ("gemini", "google"),
        )
    )


@pytest.mark.asyncio
async def test_ready_solution_tree_is_rechecked_by_existing_frontier_council_without_minting_authority() -> None:
    artifact = evaluate()
    result = await execute_verified_novel_frontier(
        gateway=FakeGateway(),
        request=VerifiedNovelFrontierRequest(
            tenant_id=TENANT,
            company_id=COMPANY,
            problem="Choose the most robust solution for the verified novel operating problem",
            task=frontier_task(),
            benchmarks=benchmarks(),
            solution_artifact=artifact,
        ),
    )
    assert result.supremacy.decision_ready is True
    assert result.supremacy.final_answer == "Novel solution synthesis after counterfactual review"
    assert result.solution_artifact_fingerprint == artifact.fingerprint
    assert result.execution_authority_granted is False
    assert result.company_truth_promoted is False
    assert result.superiority_claim_allowed is False


def test_hold_or_cross_company_artifact_cannot_enter_frontier_deliberation() -> None:
    hold = evaluate(
        evaluations=evaluations(
            scores={"solution-a": 0.80, "solution-b": 0.78, "solution-c": 0.70}
        )
    )
    with pytest.raises(ValidationError, match="novel_frontier_solution_artifact_not_ready"):
        VerifiedNovelFrontierRequest(
            tenant_id=TENANT,
            company_id=COMPANY,
            problem="Novel problem",
            task=frontier_task(),
            benchmarks=benchmarks(),
            solution_artifact=hold,
        )

    ready = evaluate()
    with pytest.raises(ValidationError, match="novel_frontier_cross_company_artifact_forbidden"):
        VerifiedNovelFrontierRequest(
            tenant_id=TENANT,
            company_id="company-b",
            problem="Novel problem",
            task=frontier_task(),
            benchmarks=benchmarks(),
            solution_artifact=ready,
        )
