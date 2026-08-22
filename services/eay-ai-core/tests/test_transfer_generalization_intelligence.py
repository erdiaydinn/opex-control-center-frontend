from __future__ import annotations

import hashlib
import json

import pytest

from app.novel_problem_solver_intelligence import (
    NovelCandidateScore,
    NovelProblemDisposition,
    NovelProblemSolutionArtifact,
)
from app.transfer_generalization_intelligence import (
    IndependentTransferEvaluation,
    TransferDisposition,
    TransferEvaluationOutcome,
    TransferGeneralizationArtifact,
    TransferScenario,
    TransferScenarioFamily,
    evaluate_transfer_generalization,
)

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


def source_artifact(
    *,
    tenant: str = TENANT,
    company: str = COMPANY,
    disposition: NovelProblemDisposition = NovelProblemDisposition.READY,
) -> NovelProblemSolutionArtifact:
    ready = disposition is NovelProblemDisposition.READY
    values = {
        "contract": "eay-novel-problem-solving-v1",
        "problem_id": PROBLEM,
        "tenant_id": tenant,
        "company_id": company,
        "investigation_fingerprint": "a" * 64,
        "solution_ids": ("solution-a", "solution-b", "solution-c"),
        "root_strategy_keys": ("architecture-first", "process-first", "data-first"),
        "candidate_scores": (
            NovelCandidateScore(
                solution_id="solution-a",
                root_strategy_key="architecture-first",
                conservative_score=0.89,
                evaluator_count=2,
                survived_falsifier_count=2,
                counterfactual_count=1,
                eligible=True,
            ),
        ),
        "selected_solution_id": "solution-a" if ready else None,
        "decisive_margin": 0.14 if ready else None,
        "disposition": disposition,
        "blockers": () if ready else ("novel_problem_decisive_margin_insufficient",),
        "evidence_refs": ("novel://source", "novel://independent-review"),
        "execution_authority_granted": False,
        "company_truth_promoted": False,
        "automatic_action_allowed": False,
        "superiority_claim_allowed": False,
    }
    draft = NovelProblemSolutionArtifact.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json", exclude={"fingerprint"})
    return NovelProblemSolutionArtifact(**values, fingerprint=_seal(payload))


def scenarios() -> tuple[TransferScenario, ...]:
    common = ("Preserve tenant isolation", "No unauthorized side effects")
    return (
        TransferScenario(
            scenario_id="near-1",
            family=TransferScenarioFamily.NEAR_DISTRIBUTION,
            description="Same mechanism under a nearby operating distribution",
            expected_solution_applicable=True,
            changed_factors=("Demand mix shifts moderately",),
            preserved_constraints=common,
            independently_designed=True,
            holdout=False,
            design_evidence_ref="design://near-1",
            evidence_refs=("scenario://near-1",),
        ),
        TransferScenario(
            scenario_id="domain-1",
            family=TransferScenarioFamily.DOMAIN_SHIFT,
            description="Transfer the mechanism into a distinct operating domain",
            expected_solution_applicable=True,
            changed_factors=("Operating domain changes",),
            preserved_constraints=common,
            challenged_assumptions=("Domain vocabulary is stable",),
            independently_designed=True,
            holdout=True,
            design_evidence_ref="design://domain-1",
            evidence_refs=("scenario://domain-1",),
        ),
        TransferScenario(
            scenario_id="time-1",
            family=TransferScenarioFamily.TEMPORAL_SHIFT,
            description="Evaluate the mechanism after a material temporal shift",
            expected_solution_applicable=True,
            changed_factors=("Baseline distribution ages",),
            preserved_constraints=common,
            challenged_assumptions=("Historical baseline remains representative",),
            independently_designed=True,
            holdout=True,
            design_evidence_ref="design://time-1",
            evidence_refs=("scenario://time-1",),
        ),
        TransferScenario(
            scenario_id="adversarial-1",
            family=TransferScenarioFamily.ADVERSARIAL_PERTURBATION,
            description="Stress the mechanism with adversarial but valid perturbation",
            expected_solution_applicable=True,
            changed_factors=("Evidence becomes deliberately misleading",),
            preserved_constraints=common,
            challenged_assumptions=("Inputs are naturally distributed",),
            independently_designed=True,
            holdout=True,
            design_evidence_ref="design://adversarial-1",
            evidence_refs=("scenario://adversarial-1",),
        ),
        TransferScenario(
            scenario_id="negative-1",
            family=TransferScenarioFamily.NEGATIVE_CONTROL,
            description="Negative control where the solution must correctly abstain",
            expected_solution_applicable=False,
            changed_factors=("Causal mechanism is intentionally absent",),
            preserved_constraints=common,
            challenged_assumptions=("The suspected mechanism is present",),
            independently_designed=True,
            holdout=True,
            design_evidence_ref="design://negative-1",
            evidence_refs=("scenario://negative-1",),
        ),
    )


def evaluations(
    *,
    outcome_overrides: dict[str, TransferEvaluationOutcome] | None = None,
    boundary_failure: str | None = None,
    non_independent: str | None = None,
    stale_evidence: str | None = None,
) -> tuple[IndependentTransferEvaluation, ...]:
    outcomes = outcome_overrides or {}
    items = []
    for scenario in scenarios():
        for index, evaluator in enumerate(("reviewer-one", "reviewer-two"), start=1):
            evidence = (
                "novel://source"
                if scenario.scenario_id == stale_evidence
                else f"transfer://{scenario.scenario_id}/{index}"
            )
            items.append(
                IndependentTransferEvaluation(
                    evaluation_id=f"eval-{scenario.scenario_id}-{index}",
                    scenario_id=scenario.scenario_id,
                    evaluator_ref=(
                        "reviewer-one"
                        if scenario.scenario_id == non_independent
                        else evaluator
                    ),
                    independent_evaluator=not (
                        scenario.scenario_id == non_independent and index == 2
                    ),
                    outcome=outcomes.get(
                        scenario.scenario_id,
                        TransferEvaluationOutcome.PASSED,
                    ),
                    boundary_respected=scenario.scenario_id != boundary_failure,
                    constraints_satisfied=True,
                    mechanism_transfer=0.88 - (index - 1) * 0.02,
                    expected_outcome_alignment=0.90 - (index - 1) * 0.02,
                    robustness=0.87 - (index - 1) * 0.02,
                    calibration=0.86 - (index - 1) * 0.02,
                    evidence_strength=0.89 - (index - 1) * 0.02,
                    unresolved_material_objections=0,
                    evidence_refs=(evidence,),
                )
            )
    return tuple(items)


def evaluate(**overrides) -> TransferGeneralizationArtifact:
    values = {
        "source": source_artifact(),
        "tenant_id": TENANT,
        "company_id": COMPANY,
        "problem_id": PROBLEM,
        "scenarios": scenarios(),
        "evaluations": evaluations(),
    }
    values.update(overrides)
    return evaluate_transfer_generalization(**values)


def test_all_transfer_families_holdouts_and_independent_evaluators_admit_bounded_claim() -> None:
    result = evaluate()
    assert result.disposition is TransferDisposition.READY
    assert result.bounded_transfer_claim_allowed is True
    assert result.universal_generalization_claim_allowed is False
    assert result.ready_fraction == 1.0
    assert result.holdout_scenario_count == 4
    assert result.worst_case_score >= 0.70
    assert set(result.tested_scope_families) == set(TransferScenarioFamily)
    assert result.generalizable_invariants == (
        "No unauthorized side effects",
        "Preserve tenant isolation",
    )
    assert "The suspected mechanism is present" in result.context_bound_assumptions
    assert result.execution_authority_granted is False
    assert result.side_effect_authority_granted is False
    assert result.company_truth_promoted is False


def test_missing_core_family_holds_instead_of_overclaiming_generalization() -> None:
    subset = tuple(
        item for item in scenarios() if item.family is not TransferScenarioFamily.NEGATIVE_CONTROL
    )
    evals = tuple(item for item in evaluations() if item.scenario_id != "negative-1")
    result = evaluate(scenarios=subset, evaluations=evals)
    assert result.disposition is TransferDisposition.HOLD
    assert result.bounded_transfer_claim_allowed is False
    assert "transfer_required_scenario_family_missing:negative_control" in result.blockers


def test_holdout_quorum_is_mandatory() -> None:
    reduced = tuple(item.model_copy(update={"holdout": False}) for item in scenarios())
    result = evaluate(scenarios=reduced)
    assert result.disposition is TransferDisposition.HOLD
    assert "transfer_holdout_scenario_quorum_missing" in result.blockers


def test_failed_or_inconclusive_transfer_scenario_forces_hold() -> None:
    failed = evaluate(
        evaluations=evaluations(
            outcome_overrides={"domain-1": TransferEvaluationOutcome.FAILED}
        )
    )
    score = next(item for item in failed.scenario_scores if item.scenario_id == "domain-1")
    assert score.eligible is False
    assert "transfer_scenario_failed" in score.blockers
    assert failed.disposition is TransferDisposition.HOLD

    inconclusive = evaluate(
        evaluations=evaluations(
            outcome_overrides={"time-1": TransferEvaluationOutcome.INCONCLUSIVE}
        )
    )
    score = next(item for item in inconclusive.scenario_scores if item.scenario_id == "time-1")
    assert "transfer_scenario_inconclusive" in score.blockers
    assert inconclusive.disposition is TransferDisposition.HOLD


def test_negative_control_must_preserve_decision_boundary() -> None:
    result = evaluate(evaluations=evaluations(boundary_failure="negative-1"))
    score = next(item for item in result.scenario_scores if item.scenario_id == "negative-1")
    assert score.eligible is False
    assert "transfer_decision_boundary_violated" in score.blockers
    assert result.bounded_transfer_claim_allowed is False


def test_two_distinct_independent_evaluators_are_required_per_scenario() -> None:
    result = evaluate(evaluations=evaluations(non_independent="adversarial-1"))
    score = next(
        item for item in result.scenario_scores if item.scenario_id == "adversarial-1"
    )
    assert score.independent_evaluator_count == 1
    assert "transfer_independent_evaluator_quorum_missing" in score.blockers
    assert result.disposition is TransferDisposition.HOLD


def test_fresh_transfer_evidence_is_required_beyond_source_solution_evidence() -> None:
    result = evaluate(evaluations=evaluations(stale_evidence="domain-1"))
    score = next(item for item in result.scenario_scores if item.scenario_id == "domain-1")
    assert "transfer_fresh_evidence_required" in score.blockers
    assert result.disposition is TransferDisposition.HOLD


def test_non_independent_scenario_design_holds() -> None:
    changed = tuple(
        item.model_copy(update={"independently_designed": False})
        if item.scenario_id == "time-1"
        else item
        for item in scenarios()
    )
    result = evaluate(scenarios=changed)
    score = next(item for item in result.scenario_scores if item.scenario_id == "time-1")
    assert "transfer_scenario_independent_design_required" in score.blockers
    assert result.disposition is TransferDisposition.HOLD


def test_source_must_be_ready_and_exactly_tenant_company_problem_bound() -> None:
    with pytest.raises(ValueError, match="transfer_requires_ready_novel_solution"):
        evaluate(source=source_artifact(disposition=NovelProblemDisposition.HOLD))

    with pytest.raises(ValueError, match="transfer_cross_tenant_source_forbidden"):
        evaluate(source=source_artifact(tenant="tenant-b"))

    with pytest.raises(ValueError, match="transfer_cross_company_source_forbidden"):
        evaluate(source=source_artifact(company="company-b"))


def test_unknown_scenario_and_duplicate_ids_are_rejected_structurally() -> None:
    duplicate = scenarios() + (scenarios()[0],)
    with pytest.raises(ValueError, match="transfer_scenario_ids_must_be_unique"):
        evaluate(scenarios=duplicate)

    unknown = list(evaluations())
    unknown[0] = unknown[0].model_copy(update={"scenario_id": "unknown-scenario"})
    with pytest.raises(ValueError, match="transfer_evaluation_references_unknown_scenario"):
        evaluate(evaluations=tuple(unknown))


def test_tampering_or_attempted_authority_escalation_is_rejected() -> None:
    result = evaluate()
    tampered = result.model_copy(update={"ready_fraction": 0.5})
    with pytest.raises(ValueError, match="transfer_generalization_fingerprint_mismatch"):
        TransferGeneralizationArtifact.model_validate(tampered.model_dump(mode="json"))

    escalated = result.model_copy(update={"execution_authority_granted": True})
    with pytest.raises(
        ValueError,
        match="transfer_generalization_never_mints_authority_or_universal_claim",
    ):
        TransferGeneralizationArtifact.model_validate(escalated.model_dump(mode="json"))

    universal = result.model_copy(update={"universal_generalization_claim_allowed": True})
    with pytest.raises(
        ValueError,
        match="transfer_generalization_never_mints_authority_or_universal_claim",
    ):
        TransferGeneralizationArtifact.model_validate(universal.model_dump(mode="json"))
