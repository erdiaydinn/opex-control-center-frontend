from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.longitudinal_method_reliability_intelligence import (
    IndependentOutcomeEvaluation,
    LongitudinalMethodReliabilityArtifact,
    MethodOutcomeEpisode,
    MethodReliabilityState,
    OutcomeEvaluationOutcome,
    evaluate_longitudinal_method_reliability,
)
from app.transfer_generalization_intelligence import (
    TransferDisposition,
    TransferGeneralizationArtifact,
    TransferScenarioFamily,
    TransferScenarioScore,
)

TENANT = "tenant-a"
COMPANY = "company-a"
PROBLEM = "novel-problem-1"
METHOD = "solution-a"
CURRENT = "regime-current"
OLD = "regime-old"
AS_OF = datetime(2026, 8, 22, 6, 0, tzinfo=timezone.utc)


def _seal(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def transfer_source(
    *,
    tenant: str = TENANT,
    company: str = COMPANY,
    disposition: TransferDisposition = TransferDisposition.READY,
) -> TransferGeneralizationArtifact:
    ready = disposition is TransferDisposition.READY
    families = tuple(TransferScenarioFamily)
    scores = tuple(
        TransferScenarioScore(
            scenario_id=f"source-{family.value}",
            family=family,
            conservative_score=0.88,
            independent_evaluator_count=2,
            eligible=ready,
            blockers=() if ready else ("source_hold",),
        )
        for family in families
    )
    values = {
        "contract": "eay-transfer-generalization-v1",
        "problem_id": PROBLEM,
        "tenant_id": tenant,
        "company_id": company,
        "source_solution_artifact_fingerprint": "a" * 64,
        "selected_solution_id": METHOD,
        "tested_scope_families": families,
        "scenario_count": 5,
        "holdout_scenario_count": 4,
        "ready_fraction": 1.0 if ready else 0.8,
        "worst_case_score": 0.88,
        "generalizable_invariants": ("Preserve tenant isolation",),
        "context_bound_assumptions": ("Historical baseline remains representative",),
        "scenario_scores": scores,
        "disposition": disposition,
        "blockers": () if ready else ("source_hold",),
        "evidence_refs": ("transfer://source", "transfer://review"),
        "bounded_transfer_claim_allowed": ready,
        "universal_generalization_claim_allowed": False,
        "company_truth_promoted": False,
        "provider_authority_granted": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
    }
    draft = TransferGeneralizationArtifact.model_construct(**values, fingerprint="0" * 64)
    return TransferGeneralizationArtifact(
        **values,
        fingerprint=_seal(draft.model_dump(mode="json", exclude={"fingerprint"})),
    )


def episode(
    episode_id: str,
    regime: str,
    day_offset: int,
    *,
    expected: bool = True,
    applied: bool = True,
    evidence: str | None = None,
    independent: bool = True,
) -> MethodOutcomeEpisode:
    observed = AS_OF - timedelta(days=20 - day_offset)
    return MethodOutcomeEpisode(
        episode_id=episode_id,
        regime_id=regime,
        description=f"Realized outcome episode {episode_id}",
        expected_method_applicable=expected,
        method_applied=applied,
        prediction_at=observed - timedelta(hours=4),
        observed_at=observed,
        independently_observed=independent,
        preserved_constraints=("Preserve tenant isolation", "No unauthorized side effects"),
        challenged_assumptions=() if expected else ("Mechanism is present",),
        outcome_evidence_refs=(evidence or f"outcome://{episode_id}",),
    )


def episodes() -> tuple[MethodOutcomeEpisode, ...]:
    return (
        episode("old-1", OLD, 1),
        episode("old-2", OLD, 2),
        episode("current-1", CURRENT, 10),
        episode("current-2", CURRENT, 11),
        episode("current-3", CURRENT, 12),
        episode("current-negative", CURRENT, 13, expected=False, applied=False),
    )


def evaluations(
    items: tuple[MethodOutcomeEpisode, ...] | None = None,
    *,
    outcome_overrides: dict[str, OutcomeEvaluationOutcome] | None = None,
    duplicate_evaluator_episode: str | None = None,
    boundary_failure: str | None = None,
    objections_episode: str | None = None,
    score_override: dict[str, float] | None = None,
    stale_evidence_episode: str | None = None,
) -> tuple[IndependentOutcomeEvaluation, ...]:
    items = items or episodes()
    overrides = outcome_overrides or {}
    scores = score_override or {}
    result = []
    for item in items:
        for index, evaluator in enumerate(("reviewer-one", "reviewer-two"), start=1):
            score = scores.get(item.episode_id, 0.88 - (index - 1) * 0.01)
            result.append(
                IndependentOutcomeEvaluation(
                    evaluation_id=f"eval-{item.episode_id}-{index}",
                    episode_id=item.episode_id,
                    evaluator_ref=(
                        "reviewer-one"
                        if item.episode_id == duplicate_evaluator_episode
                        else evaluator
                    ),
                    independent_evaluator=True,
                    outcome=overrides.get(item.episode_id, OutcomeEvaluationOutcome.PASSED),
                    boundary_respected=item.episode_id != boundary_failure,
                    constraints_satisfied=True,
                    outcome_alignment=score,
                    mechanism_reliability=score,
                    regime_robustness=score,
                    calibration=score,
                    evidence_strength=score,
                    unresolved_material_objections=(
                        1 if item.episode_id == objections_episode else 0
                    ),
                    evidence_refs=(
                        "transfer://source"
                        if item.episode_id == stale_evidence_episode
                        else f"evaluation://{item.episode_id}/{index}",
                    ),
                )
            )
    return tuple(result)


def assess(
    *,
    source: TransferGeneralizationArtifact | None = None,
    items: tuple[MethodOutcomeEpisode, ...] | None = None,
    evals: tuple[IndependentOutcomeEvaluation, ...] | None = None,
    current_regime: str = CURRENT,
    as_of: datetime = AS_OF,
) -> LongitudinalMethodReliabilityArtifact:
    items = items or episodes()
    return evaluate_longitudinal_method_reliability(
        source=source or transfer_source(),
        tenant_id=TENANT,
        company_id=COMPANY,
        problem_id=PROBLEM,
        method_id=METHOD,
        current_regime_id=current_regime,
        assessment_as_of=as_of,
        episodes=items,
        evaluations=evals or evaluations(items),
    )


def test_stable_realized_outcomes_across_regimes_admit_only_bounded_current_trust() -> None:
    result = assess()
    assert result.state is MethodReliabilityState.TRUSTED
    assert result.bounded_current_regime_reliability_claim_allowed is True
    assert result.universal_reliability_claim_allowed is False
    assert result.distinct_regime_count == 2
    assert result.current_regime_episode_count == 4
    assert result.current_negative_control_count == 1
    assert result.current_regime_worst_score >= 0.75
    assert result.company_truth_promoted is False
    assert result.execution_authority_granted is False
    assert result.side_effect_authority_granted is False


def test_current_regime_failure_overrides_historical_successes() -> None:
    result = assess(
        evals=evaluations(
            outcome_overrides={"current-2": OutcomeEvaluationOutcome.FAILED}
        )
    )
    assert result.state is MethodReliabilityState.DISTRUSTED
    assert "method_reliability_recovery_hysteresis_not_satisfied" in result.blockers
    assert result.bounded_current_regime_reliability_claim_allowed is False


def test_inconclusive_current_outcome_and_negative_control_overgeneralization_distrust() -> None:
    inconclusive = assess(
        evals=evaluations(
            outcome_overrides={"current-2": OutcomeEvaluationOutcome.INCONCLUSIVE}
        )
    )
    assert inconclusive.state is MethodReliabilityState.DISTRUSTED

    changed = tuple(
        item.model_copy(update={"method_applied": True})
        if item.episode_id == "current-negative"
        else item
        for item in episodes()
    )
    overgeneralized = assess(items=changed, evals=evaluations(changed))
    assert overgeneralized.state is MethodReliabilityState.DISTRUSTED


def test_future_leakage_and_prediction_after_observation_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="method_reliability_prediction_must_precede_observation",
    ):
        MethodOutcomeEpisode(
            episode_id="bad-time",
            regime_id=CURRENT,
            description="Invalid chronological realized outcome",
            expected_method_applicable=True,
            method_applied=True,
            prediction_at=AS_OF,
            observed_at=AS_OF,
            independently_observed=True,
            preserved_constraints=("Preserve tenant isolation",),
            outcome_evidence_refs=("outcome://bad",),
        )

    future = list(episodes())
    future[-1] = future[-1].model_copy(
        update={
            "prediction_at": AS_OF + timedelta(hours=1),
            "observed_at": AS_OF + timedelta(hours=2),
        }
    )
    with pytest.raises(ValueError, match="method_reliability_future_outcome_evidence_forbidden"):
        assess(items=tuple(future), evals=evaluations(tuple(future)))


def test_insufficient_current_sample_or_evaluator_quorum_is_limited() -> None:
    reduced = tuple(item for item in episodes() if item.episode_id != "current-3")
    limited = assess(items=reduced, evals=evaluations(reduced))
    assert limited.state is MethodReliabilityState.LIMITED
    assert "method_reliability_current_regime_episode_quorum_missing" in limited.blockers

    quorum = assess(evals=evaluations(duplicate_evaluator_episode="current-1"))
    assert quorum.state is MethodReliabilityState.LIMITED
    assert "method_reliability_current_regime_not_fully_qualified" in quorum.blockers


def test_near_threshold_or_unresolved_objection_never_becomes_trusted() -> None:
    near = assess(evals=evaluations(score_override={"current-1": 0.77}))
    assert near.state is MethodReliabilityState.LIMITED

    objection = assess(evals=evaluations(objections_episode="current-2"))
    assert objection.state is MethodReliabilityState.DISTRUSTED


def test_fresh_realized_and_evaluation_evidence_are_required() -> None:
    changed = tuple(
        item.model_copy(update={"outcome_evidence_refs": ("transfer://source",)})
        if item.episode_id == "current-1"
        else item
        for item in episodes()
    )
    stale_outcome = assess(items=changed, evals=evaluations(changed))
    assert stale_outcome.state is MethodReliabilityState.LIMITED

    stale_eval = assess(evals=evaluations(stale_evidence_episode="current-1"))
    assert stale_eval.state is MethodReliabilityState.LIMITED


def test_recovery_requires_multiple_clean_episodes_not_one_lucky_success() -> None:
    base = episodes()
    failed = evaluations(
        base,
        outcome_overrides={"current-2": OutcomeEvaluationOutcome.FAILED},
    )
    assert assess(items=base, evals=failed).state is MethodReliabilityState.DISTRUSTED

    extra = (
        episode("current-4", CURRENT, 14),
        episode("current-5", CURRENT, 15),
    )
    recovered_items = base + extra
    recovered_evals = evaluations(
        recovered_items,
        outcome_overrides={"current-2": OutcomeEvaluationOutcome.FAILED},
    )
    recovered = assess(items=recovered_items, evals=recovered_evals)
    assert recovered.recovery_clean_episode_count == 3
    assert recovered.state is MethodReliabilityState.TRUSTED


def test_source_must_be_ready_and_exactly_bound() -> None:
    with pytest.raises(ValueError, match="method_reliability_requires_ready_transfer_source"):
        assess(source=transfer_source(disposition=TransferDisposition.HOLD))

    with pytest.raises(ValueError, match="method_reliability_cross_tenant_source_forbidden"):
        assess(source=transfer_source(tenant="tenant-b"))

    with pytest.raises(ValueError, match="method_reliability_cross_company_source_forbidden"):
        assess(source=transfer_source(company="company-b"))


def test_duplicate_ids_unknown_refs_and_tampering_are_rejected() -> None:
    duplicate = episodes() + (episodes()[0],)
    with pytest.raises(ValueError, match="method_reliability_episode_ids_must_be_unique"):
        assess(items=duplicate, evals=evaluations(duplicate))

    unknown = list(evaluations())
    unknown[0] = unknown[0].model_copy(update={"episode_id": "unknown-episode"})
    with pytest.raises(
        ValueError,
        match="method_reliability_evaluation_references_unknown_episode",
    ):
        assess(evals=tuple(unknown))

    result = assess()
    tampered = result.model_copy(update={"current_regime_worst_score": 0.1})
    with pytest.raises(ValueError, match="method_reliability_fingerprint_mismatch"):
        LongitudinalMethodReliabilityArtifact.model_validate(tampered.model_dump(mode="json"))


def test_authority_escalation_is_rejected() -> None:
    result = assess()
    escalated = result.model_copy(update={"automatic_model_weight_update_allowed": True})
    with pytest.raises(
        ValueError,
        match="method_reliability_never_mints_authority_or_universal_claim",
    ):
        LongitudinalMethodReliabilityArtifact.model_validate(escalated.model_dump(mode="json"))
