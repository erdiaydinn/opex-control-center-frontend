from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.autonomous_investigator import (
    FalsificationResult,
    FalsificationVerdict,
    InvestigatorDisposition,
    InvestigatorHypothesis,
    InvestigatorProblem,
    ProblemNovelty,
    SourceIndependenceBinding,
    build_investigator_lesson,
    calibrate_investigator_lessons,
    evaluate_autonomous_investigation,
    plan_autonomous_research,
)
from app.outcome_learning import (
    DecisionLearningRecord,
    ExpectedMetricOutcome,
    ObservedMetricOutcome,
    assess_decision_outcome,
)
from app.research_engine import ResearchEvidence, ResearchRisk, ResearchRole, SourceTier
from app.world_model import EntityKind, WorldEntity, build_world_snapshot

NOW = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)


def problem(**updates) -> InvestigatorProblem:
    values = {
        "problem_id": "problem:orders-down",
        "tenant_id": "tenant-a",
        "company_id": "company-a",
        "question": "Why did store orders fall unexpectedly despite normal staffing?",
        "domains": ("operations", "weather", "commerce"),
        "as_of": NOW,
        "risk": ResearchRisk.HIGH,
        "novelty": ProblemNovelty.NOVEL,
        "minimum_independent_sources": 2,
        "maximum_world_age_seconds": 900,
        "evidence_freshness_seconds": 86_400,
    }
    values.update(updates)
    return InvestigatorProblem(**values)


def hypotheses() -> tuple[InvestigatorHypothesis, ...]:
    return (
        InvestigatorHypothesis(
            hypothesis_id="h-demand",
            label="Demand shifted because of an external local event",
            claim_key="claim:demand-event",
            required_falsification_test_ids=("f-demand",),
        ),
        InvestigatorHypothesis(
            hypothesis_id="h-stock",
            label="Availability degradation suppressed customer conversion",
            claim_key="claim:availability",
            required_falsification_test_ids=("f-stock",),
        ),
        InvestigatorHypothesis(
            hypothesis_id="h-platform",
            label="A platform incident reduced order intake",
            claim_key="claim:platform",
            required_falsification_test_ids=("f-platform",),
        ),
    )


def world(*, as_of: datetime = NOW, tenant_id: str = "tenant-a"):
    return build_world_snapshot(
        tenant_id=tenant_id,
        as_of=as_of,
        entities=[
            WorldEntity(
                entity_id="store:fulya",
                tenant_id=tenant_id,
                kind=EntityKind.STORE,
                display_name="Fulya",
            )
        ],
        assertions=[],
    )


def item(
    evidence_id: str,
    claim_key: str,
    publisher: str,
    *,
    tier: SourceTier,
    supports: bool = False,
    contradicts: bool = False,
    fetched_at: datetime = NOW,
) -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id=evidence_id,
        claim_key=claim_key,
        claim_value=f"value:{evidence_id}",
        source_url=f"https://{publisher}.example/{evidence_id}",
        source_domain=f"{publisher}.example",
        source_tier=tier,
        publisher_key=publisher,
        published_at=fetched_at - timedelta(minutes=5),
        fetched_at=fetched_at,
        supports_claim=supports,
        contradicts_claim=contradicts,
        evidence_ref=f"evidence://{evidence_id}",
    )


def evidence_set() -> tuple[ResearchEvidence, ...]:
    return (
        item("d1", "claim:demand-event", "official", tier=SourceTier.PRIMARY, supports=True),
        item(
            "d2",
            "claim:demand-event",
            "independent-news",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            supports=True,
        ),
        item(
            "d3",
            "claim:demand-event",
            "skeptic-blog",
            tier=SourceTier.DISCOVERY_ONLY,
            contradicts=True,
        ),
        item("s1", "claim:availability", "catalog", tier=SourceTier.PRIMARY, supports=True),
        item(
            "s2",
            "claim:availability",
            "inventory",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            contradicts=True,
        ),
        item(
            "s3",
            "claim:availability",
            "ops-check",
            tier=SourceTier.REPUTABLE_SECONDARY,
            contradicts=True,
        ),
        item("p1", "claim:platform", "status", tier=SourceTier.PRIMARY, supports=True),
        item(
            "p2",
            "claim:platform",
            "telemetry",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            contradicts=True,
        ),
        item(
            "p3",
            "claim:platform",
            "incident-review",
            tier=SourceTier.REPUTABLE_SECONDARY,
            contradicts=True,
        ),
    )


def bindings(evidence: tuple[ResearchEvidence, ...]) -> tuple[SourceIndependenceBinding, ...]:
    return tuple(
        SourceIndependenceBinding(
            evidence_id=item.evidence_id,
            source_family_key=f"family:{item.publisher_key}",
        )
        for item in evidence
    )


def falsifications() -> tuple[FalsificationResult, ...]:
    return (
        FalsificationResult(
            test_id="f-demand",
            hypothesis_id="h-demand",
            verdict=FalsificationVerdict.SURVIVED,
            evidence_refs=("evidence://f-demand",),
            completed_at=NOW,
        ),
        FalsificationResult(
            test_id="f-stock",
            hypothesis_id="h-stock",
            verdict=FalsificationVerdict.REFUTED,
            evidence_refs=("evidence://f-stock",),
            completed_at=NOW,
        ),
        FalsificationResult(
            test_id="f-platform",
            hypothesis_id="h-platform",
            verdict=FalsificationVerdict.REFUTED,
            evidence_refs=("evidence://f-platform",),
            completed_at=NOW,
        ),
    )


def grounded_outcome(*, tenant_id: str = "tenant-a"):
    decision = DecisionLearningRecord(
        decision_id=f"decision:orders-down:{tenant_id}",
        tenant_id=tenant_id,
        decided_at=NOW,
        decision_type="root-cause-investigation",
        recommendation_ref="artifact://decision/root-cause",
        expected_outcomes=(
            ExpectedMetricOutcome(
                metric_key="orders",
                baseline_value=100.0,
                expected_value=110.0,
                unit="orders",
                confidence=0.8,
                evidence_refs=("evidence://forecast",),
            ),
        ),
        decision_evidence_refs=("evidence://decision",),
    )
    return assess_decision_outcome(
        decision=decision,
        outcomes=[
            ObservedMetricOutcome(
                metric_key="orders",
                observed_value=90.0,
                unit="orders",
                observed_at=NOW + timedelta(hours=2),
                governed_truth_ref="truth://orders/observed",
                evidence_refs=("evidence://orders/observed",),
            )
        ],
    )


def decision_ready_report():
    evidence = evidence_set()
    return evaluate_autonomous_investigation(
        problem=problem(),
        world=world(),
        hypotheses=hypotheses(),
        evidence=evidence,
        source_bindings=bindings(evidence),
        falsification_results=falsifications(),
    )


def test_novel_problem_requires_three_competing_hypotheses_and_contradiction_search() -> None:
    with pytest.raises(ValueError, match="competing_hypotheses_insufficient"):
        plan_autonomous_research(problem=problem(), hypotheses=hypotheses()[:2])

    plans = plan_autonomous_research(problem=problem(), hypotheses=hypotheses())

    assert len(plans) == 3
    assert all(plan.mission.contradiction_search_required for plan in plans)
    assert all(
        any(task.role is ResearchRole.CONTRADICTION for task in plan.mission.tasks)
        for plan in plans
    )
    assert all(plan.mission.primary_source_required for plan in plans)


def test_stale_company_world_forces_hold_instead_of_reasoning_through_missing_reality() -> None:
    evidence = evidence_set()
    report = evaluate_autonomous_investigation(
        problem=problem(maximum_world_age_seconds=60),
        world=world(as_of=NOW - timedelta(minutes=10)),
        hypotheses=hypotheses(),
        evidence=evidence,
        source_bindings=bindings(evidence),
        falsification_results=falsifications(),
    )

    assert report.disposition is InvestigatorDisposition.HOLD
    assert "investigator_world_state_stale" in report.blockers
    assert report.execution_authority_granted is False
    assert report.production_truth_promoted is False


def test_correlated_publishers_cannot_fake_independent_source_quorum() -> None:
    evidence = evidence_set()
    source_bindings = list(bindings(evidence))
    source_bindings = [
        binding.model_copy(update={"source_family_key": "family:same-network"})
        if binding.evidence_id in {"d1", "d2", "d3"}
        else binding
        for binding in source_bindings
    ]

    report = evaluate_autonomous_investigation(
        problem=problem(),
        world=world(),
        hypotheses=hypotheses(),
        evidence=evidence,
        source_bindings=tuple(source_bindings),
        falsification_results=falsifications(),
    )

    leader = next(item for item in report.research_states if item.hypothesis_id == "h-demand")
    assert leader.independent_source_family_count == 1
    assert "investigator_independent_source_family_quorum_missing" in leader.blockers
    assert report.disposition is not InvestigatorDisposition.DECISION_READY


def test_active_falsification_resolves_weak_contestation_without_hiding_raw_assessment() -> None:
    report = decision_ready_report()

    assert report.ranking is not None
    assert report.ranking.leading_hypothesis_id == "h-demand"
    assert report.ranking.decisive is True
    leader = next(item for item in report.research_states if item.hypothesis_id == "h-demand")
    assert leader.assessment.verdict.value == "contested"
    assert leader.material_contestation_resolved is True
    assert report.disposition is InvestigatorDisposition.DECISION_READY
    assert report.blockers == ()
    assert report.calibrated_confidence_cap <= 0.60
    assert report.firm_company_claim_authorized is False
    assert report.execution_authority_granted is False


def test_missing_falsification_prevents_favorite_hypothesis_from_becoming_decision_ready() -> None:
    evidence = evidence_set()
    report = evaluate_autonomous_investigation(
        problem=problem(),
        world=world(),
        hypotheses=hypotheses(),
        evidence=evidence,
        source_bindings=bindings(evidence),
        falsification_results=falsifications()[1:],
    )

    assert report.disposition is InvestigatorDisposition.HOLD
    assert "investigator_falsification_incomplete" in report.blockers
    assert "research_material_contradiction_unresolved" in report.blockers
    assert "h-demand:run_falsification:f-demand" in report.next_research_tasks


def test_stronger_refuting_evidence_can_overturn_the_initial_favorite() -> None:
    evidence = list(evidence_set())
    evidence.extend(
        (
            item(
                "d4",
                "claim:demand-event",
                "official-two",
                tier=SourceTier.PRIMARY,
                contradicts=True,
            ),
            item(
                "s4",
                "claim:availability",
                "catalog-two",
                tier=SourceTier.PRIMARY,
                supports=True,
            ),
            item(
                "s5",
                "claim:availability",
                "inventory-two",
                tier=SourceTier.AUTHORITATIVE_SECONDARY,
                supports=True,
            ),
        )
    )
    evidence_tuple = tuple(evidence)
    falsification = (
        FalsificationResult(
            test_id="f-demand",
            hypothesis_id="h-demand",
            verdict=FalsificationVerdict.REFUTED,
            evidence_refs=("evidence://d4",),
            completed_at=NOW,
        ),
        FalsificationResult(
            test_id="f-stock",
            hypothesis_id="h-stock",
            verdict=FalsificationVerdict.SURVIVED,
            evidence_refs=("evidence://s4", "evidence://s5"),
            completed_at=NOW,
        ),
        FalsificationResult(
            test_id="f-platform",
            hypothesis_id="h-platform",
            verdict=FalsificationVerdict.REFUTED,
            evidence_refs=("evidence://p2",),
            completed_at=NOW,
        ),
    )

    report = evaluate_autonomous_investigation(
        problem=problem(),
        world=world(),
        hypotheses=hypotheses(),
        evidence=evidence_tuple,
        source_bindings=bindings(evidence_tuple),
        falsification_results=falsification,
    )

    assert report.ranking is not None
    assert report.ranking.leading_hypothesis_id == "h-stock"
    assert report.ranking.leading_hypothesis_id != "h-demand"


def test_wrong_prediction_becomes_grounded_recallable_lesson_not_self_modified_truth() -> None:
    report = decision_ready_report()
    lesson, episode = build_investigator_lesson(
        report=report,
        resolved_hypothesis_id="h-stock",
        outcome=grounded_outcome(),
        recorded_at=NOW + timedelta(hours=3),
    )

    assert lesson.prediction_correct is False
    assert lesson.brier_score > 0.0
    assert lesson.suggested_confidence_multiplier <= 0.70
    assert "investigator_leading_hypothesis_was_wrong" in lesson.failure_codes
    assert lesson.model_weights_mutated is False
    assert lesson.business_policy_mutated is False
    assert episode.kind.value == "lesson"
    assert episode.model_summary_is_truth is False
    assert "failure:investigator_leading_hypothesis_was_wrong" in episode.tags


def test_multiple_grounded_errors_produce_bounded_company_scoped_calibration() -> None:
    report = decision_ready_report()
    lesson_one, _ = build_investigator_lesson(
        report=report,
        resolved_hypothesis_id="h-stock",
        outcome=grounded_outcome(),
        recorded_at=NOW + timedelta(hours=3),
    )
    second_outcome = grounded_outcome()
    second_outcome = second_outcome.model_copy(update={"decision_id": "decision:orders-down:second"})
    lesson_two, _ = build_investigator_lesson(
        report=report,
        resolved_hypothesis_id="h-demand",
        outcome=second_outcome,
        recorded_at=NOW + timedelta(hours=4),
    )

    profile = calibrate_investigator_lessons((lesson_one, lesson_two))

    assert profile.tenant_id == "tenant-a"
    assert profile.company_id == "company-a"
    assert profile.sample_count == 2
    assert profile.mean_brier_score > 0.0
    assert profile.prediction_error_rate == 0.5
    assert profile.suggested_confidence_multiplier < 1.0
    assert profile.automatic_activation_allowed is False
    assert profile.model_weights_mutated is False
    assert profile.business_policy_mutated is False


def test_learning_rejects_cross_tenant_outcome_and_cross_company_calibration() -> None:
    report = decision_ready_report()
    with pytest.raises(ValueError, match="investigator_lesson_tenant_mismatch"):
        build_investigator_lesson(
            report=report,
            resolved_hypothesis_id="h-demand",
            outcome=grounded_outcome(tenant_id="tenant-b"),
            recorded_at=NOW + timedelta(hours=2),
        )

    lesson, _ = build_investigator_lesson(
        report=report,
        resolved_hypothesis_id="h-stock",
        outcome=grounded_outcome(),
        recorded_at=NOW + timedelta(hours=3),
    )
    other = lesson.model_copy(update={"company_id": "company-b"})
    with pytest.raises(ValueError, match="investigator_calibration_scope_mismatch"):
        calibrate_investigator_lessons((lesson, other))


def test_future_world_snapshot_is_rejected_and_no_evidence_never_guesses() -> None:
    with pytest.raises(ValueError, match="world_snapshot_from_future"):
        evaluate_autonomous_investigation(
            problem=problem(),
            world=world(as_of=NOW + timedelta(seconds=1)),
            hypotheses=hypotheses(),
            evidence=(),
            source_bindings=(),
            falsification_results=(),
        )

    report = evaluate_autonomous_investigation(
        problem=problem(),
        world=world(),
        hypotheses=hypotheses(),
        evidence=(),
        source_bindings=(),
        falsification_results=(),
    )
    assert report.disposition is InvestigatorDisposition.RESEARCH_MORE
    assert report.ranking is None
    assert report.calibrated_confidence_cap <= 0.20
    assert report.execution_authority_granted is False
