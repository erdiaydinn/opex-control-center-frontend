from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.adaptive_epistemic_control import (
    EpistemicMoveKind,
    EpistemicRoundObservation,
    EpistemicStrategy,
    WorldSourceValueSignal,
    plan_adaptive_epistemic_round,
    prioritize_world_refresh,
    score_epistemic_benchmark,
)
from app.autonomous_investigator import (
    FalsificationResult,
    FalsificationVerdict,
    InvestigatorCalibrationProfile,
    InvestigatorHypothesis,
    InvestigatorProblem,
    ProblemNovelty,
    SourceIndependenceBinding,
    evaluate_autonomous_investigation,
)
from app.continuous_world_understanding import (
    SourceFreshnessExpectation,
    SourcePulse,
    assess_continuous_world,
)
from app.real_world_timeline import TimelineAuthorityClass
from app.research_engine import ResearchEvidence, ResearchRisk, SourceTier
from app.world_model import EntityKind, WorldEntity, build_world_snapshot

NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


def _problem(*, company_id: str = "company-a") -> InvestigatorProblem:
    return InvestigatorProblem(
        problem_id="problem:orders-down",
        tenant_id="tenant-a",
        company_id=company_id,
        question="Why did store orders fall unexpectedly despite normal staffing?",
        domains=("operations", "weather", "commerce"),
        as_of=NOW,
        risk=ResearchRisk.HIGH,
        novelty=ProblemNovelty.NOVEL,
        minimum_independent_sources=2,
        maximum_world_age_seconds=900,
        evidence_freshness_seconds=86_400,
    )


def _hypotheses() -> tuple[InvestigatorHypothesis, ...]:
    return (
        InvestigatorHypothesis(
            hypothesis_id="h-demand",
            label="External local event reduced customer demand",
            claim_key="claim:demand",
            required_falsification_test_ids=("f-demand",),
        ),
        InvestigatorHypothesis(
            hypothesis_id="h-stock",
            label="Availability degradation suppressed conversion",
            claim_key="claim:stock",
            required_falsification_test_ids=("f-stock",),
        ),
        InvestigatorHypothesis(
            hypothesis_id="h-platform",
            label="A platform incident reduced order intake",
            claim_key="claim:platform",
            required_falsification_test_ids=("f-platform",),
        ),
    )


def _world(*, as_of: datetime = NOW):
    return build_world_snapshot(
        tenant_id="tenant-a",
        as_of=as_of,
        entities=(
            WorldEntity(
                entity_id="store:fulya",
                tenant_id="tenant-a",
                kind=EntityKind.STORE,
                display_name="Fulya",
            ),
        ),
        assertions=(),
    )


def _evidence_item(
    evidence_id: str,
    claim_key: str,
    publisher: str,
    *,
    tier: SourceTier,
    supports: bool = False,
    contradicts: bool = False,
) -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id=evidence_id,
        claim_key=claim_key,
        claim_value=f"value:{evidence_id}",
        source_url=f"https://{publisher}.example/{evidence_id}",
        source_domain=f"{publisher}.example",
        source_tier=tier,
        publisher_key=publisher,
        published_at=NOW - timedelta(minutes=10),
        fetched_at=NOW,
        supports_claim=supports,
        contradicts_claim=contradicts,
        evidence_ref=f"evidence://{evidence_id}",
    )


def _evidence() -> tuple[ResearchEvidence, ...]:
    return (
        _evidence_item("d1", "claim:demand", "official", tier=SourceTier.PRIMARY, supports=True),
        _evidence_item(
            "d2",
            "claim:demand",
            "news",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            supports=True,
        ),
        _evidence_item(
            "d3",
            "claim:demand",
            "skeptic",
            tier=SourceTier.DISCOVERY_ONLY,
            contradicts=True,
        ),
        _evidence_item("s1", "claim:stock", "catalog", tier=SourceTier.PRIMARY, supports=True),
        _evidence_item(
            "s2",
            "claim:stock",
            "inventory",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            contradicts=True,
        ),
        _evidence_item(
            "s3",
            "claim:stock",
            "ops",
            tier=SourceTier.REPUTABLE_SECONDARY,
            contradicts=True,
        ),
        _evidence_item("p1", "claim:platform", "status", tier=SourceTier.PRIMARY, supports=True),
        _evidence_item(
            "p2",
            "claim:platform",
            "telemetry",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            contradicts=True,
        ),
        _evidence_item(
            "p3",
            "claim:platform",
            "review",
            tier=SourceTier.REPUTABLE_SECONDARY,
            contradicts=True,
        ),
    )


def _bindings(evidence: tuple[ResearchEvidence, ...]) -> tuple[SourceIndependenceBinding, ...]:
    return tuple(
        SourceIndependenceBinding(
            evidence_id=item.evidence_id,
            source_family_key=f"family:{item.publisher_key}",
        )
        for item in evidence
    )


def _falsifications(*, include_demand: bool = True) -> tuple[FalsificationResult, ...]:
    values = [
        FalsificationResult(
            test_id="f-stock",
            hypothesis_id="h-stock",
            verdict=FalsificationVerdict.REFUTED,
            evidence_refs=("evidence://s2",),
            completed_at=NOW,
        ),
        FalsificationResult(
            test_id="f-platform",
            hypothesis_id="h-platform",
            verdict=FalsificationVerdict.REFUTED,
            evidence_refs=("evidence://p2",),
            completed_at=NOW,
        ),
    ]
    if include_demand:
        values.insert(
            0,
            FalsificationResult(
                test_id="f-demand",
                hypothesis_id="h-demand",
                verdict=FalsificationVerdict.SURVIVED,
                evidence_refs=("evidence://d3",),
                completed_at=NOW,
            ),
        )
    return tuple(values)


def _report(*, include_demand_falsification: bool = True):
    evidence = _evidence()
    return evaluate_autonomous_investigation(
        problem=_problem(),
        world=_world(),
        hypotheses=_hypotheses(),
        evidence=evidence,
        source_bindings=_bindings(evidence),
        falsification_results=_falsifications(
            include_demand=include_demand_falsification
        ),
    )


def _history(report, count: int, *, strategy: EpistemicStrategy) -> tuple[EpistemicRoundObservation, ...]:
    leader_id = report.ranking.leading_hypothesis_id if report.ranking else None
    confidence = report.ranking.assessments[0].confidence if report.ranking else 0.0
    margin = report.ranking.leading_margin if report.ranking else None
    evidence_refs = {
        ref
        for state in report.research_states
        for ref in state.assessment.evidence_refs
    }
    return tuple(
        EpistemicRoundObservation(
            round_index=index,
            report_fingerprint=report.fingerprint,
            leading_hypothesis_id=leader_id,
            leading_confidence=confidence,
            leading_margin=margin,
            evidence_ref_count=len(evidence_refs),
            unresolved_task_count=len(report.next_research_tasks),
            selected_probe_id="probe:repeated",
            selected_strategy=strategy,
        )
        for index in range(count)
    )


def test_missing_falsification_is_selected_as_high_value_next_probe() -> None:
    report = _report(include_demand_falsification=False)

    directive = plan_adaptive_epistemic_round(
        problem=_problem(),
        report=report,
        round_index=0,
    )

    assert directive.move_kind is EpistemicMoveKind.PROBE
    assert directive.selected_probe is not None
    assert directive.selected_probe.strategy is EpistemicStrategy.FALSIFICATION
    assert "run_falsification:f-demand" in directive.selected_probe.task_ref
    assert directive.selected_probe.expected_information_gain >= 0.18
    assert directive.automatic_research_execution_allowed is False
    assert directive.execution_authority_granted is False
    assert directive.direct_provider_call_allowed is False


def test_repeated_no_gain_rounds_switch_research_strategy() -> None:
    report = _report(include_demand_falsification=False)
    history = _history(report, 2, strategy=EpistemicStrategy.FALSIFICATION)

    directive = plan_adaptive_epistemic_round(
        problem=_problem(),
        report=report,
        round_index=2,
        history=history,
    )

    assert directive.stall_count >= 2
    assert directive.move_kind is EpistemicMoveKind.SWITCH_STRATEGY
    assert directive.selected_probe is not None
    assert directive.selected_probe.strategy is not EpistemicStrategy.FALSIFICATION
    assert "epistemic_repeated_stall_detected" in directive.reason_codes


def test_prolonged_stall_on_novel_problem_expands_hypothesis_space() -> None:
    report = _report(include_demand_falsification=False)
    history = _history(report, 3, strategy=EpistemicStrategy.CONTRADICTION_FIRST)

    directive = plan_adaptive_epistemic_round(
        problem=_problem(),
        report=report,
        round_index=3,
        history=history,
    )

    assert directive.stall_count >= 3
    assert directive.move_kind is EpistemicMoveKind.EXPAND_HYPOTHESIS_SPACE
    assert directive.selected_probe is None
    assert "epistemic_novel_problem_requires_alternative_hypothesis" in directive.reason_codes
    assert directive.firm_company_claim_authorized is False
    assert directive.production_truth_promoted is False


def test_grounded_error_calibration_demands_more_evidence_instead_of_self_modifying() -> None:
    report = _report()
    calibration = InvestigatorCalibrationProfile(
        tenant_id="tenant-a",
        company_id="company-a",
        sample_count=5,
        mean_brier_score=0.42,
        prediction_error_rate=0.60,
        suggested_confidence_multiplier=0.50,
        lesson_fingerprints=("a" * 64,),
        evidence_refs=("truth://measured-outcomes",),
    )

    directive = plan_adaptive_epistemic_round(
        problem=_problem(),
        report=report,
        round_index=1,
        calibration=calibration,
    )

    assert directive.calibration_multiplier == 0.50
    assert directive.effective_leading_confidence == pytest.approx(
        directive.raw_leading_confidence * 0.50,
        abs=1e-6,
    )
    assert directive.move_kind is not EpistemicMoveKind.STOP_EVIDENCE_SUFFICIENT
    assert directive.selected_probe is not None
    assert directive.selected_probe.strategy is EpistemicStrategy.CONTRADICTION_FIRST
    assert directive.automatic_model_weight_update_allowed is False
    assert directive.automatic_policy_update_allowed is False


def test_cross_company_calibration_is_rejected_before_it_can_influence_reasoning() -> None:
    report = _report()
    calibration = InvestigatorCalibrationProfile(
        tenant_id="tenant-a",
        company_id="company-b",
        sample_count=1,
        mean_brier_score=0.5,
        prediction_error_rate=1.0,
        suggested_confidence_multiplier=0.5,
        lesson_fingerprints=("b" * 64,),
        evidence_refs=("truth://other-company",),
    )

    with pytest.raises(ValueError, match="epistemic_calibration_company_mismatch"):
        plan_adaptive_epistemic_round(
            problem=_problem(),
            report=report,
            round_index=1,
            calibration=calibration,
        )


def test_bounded_research_holds_instead_of_looping_forever() -> None:
    report = _report(include_demand_falsification=False)

    directive = plan_adaptive_epistemic_round(
        problem=_problem(),
        report=report,
        round_index=8,
    )

    assert directive.move_kind is EpistemicMoveKind.HOLD_LIMIT_REACHED
    assert "epistemic_unresolved_after_bounded_research" in directive.blockers
    assert directive.selected_probe is None


def test_stale_high_value_live_source_outranks_fresh_low_value_source() -> None:
    current = _world(as_of=NOW)
    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=NOW,
        current_world=current,
        source_expectations=(
            SourceFreshnessExpectation(
                source_key="orders-live",
                maximum_silence_seconds=120,
                required_for_live_truth=True,
            ),
            SourceFreshnessExpectation(
                source_key="weather-context",
                maximum_silence_seconds=3600,
                required_for_live_truth=False,
            ),
        ),
        source_pulses=(
            SourcePulse(
                source_key="orders-live",
                observed_at=NOW - timedelta(minutes=10),
                authority_class=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
                evidence_ref="heartbeat://orders/stale",
            ),
            SourcePulse(
                source_key="weather-context",
                observed_at=NOW - timedelta(seconds=30),
                authority_class=TimelineAuthorityClass.VERIFIED_EXTERNAL,
                evidence_ref="heartbeat://weather/fresh",
            ),
        ),
    )

    priorities = prioritize_world_refresh(
        assessment=assessment,
        expectations=(
            SourceFreshnessExpectation(
                source_key="orders-live",
                maximum_silence_seconds=120,
                required_for_live_truth=True,
            ),
            SourceFreshnessExpectation(
                source_key="weather-context",
                maximum_silence_seconds=3600,
                required_for_live_truth=False,
            ),
        ),
        value_signals=(
            WorldSourceValueSignal(
                source_key="orders-live",
                business_importance=1.0,
                volatility=0.90,
                contradiction_risk=0.70,
                information_gain_hint=0.95,
            ),
            WorldSourceValueSignal(
                source_key="weather-context",
                business_importance=0.20,
                volatility=0.20,
                contradiction_risk=0.0,
                information_gain_hint=0.30,
            ),
        ),
    )

    assert priorities[0].source_key == "orders-live"
    assert priorities[0].priority_score > priorities[1].priority_score
    assert priorities[0].freshness_pressure == 1.0
    assert priorities[0].automatic_refresh_allowed is False
    assert priorities[0].execution_authority_granted is False


def test_world_refresh_rejects_unknown_source_value_signal() -> None:
    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=NOW,
        current_world=_world(),
        source_expectations=(
            SourceFreshnessExpectation(
                source_key="orders-live",
                maximum_silence_seconds=120,
            ),
        ),
        source_pulses=(
            SourcePulse(
                source_key="orders-live",
                observed_at=NOW,
                authority_class=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
                evidence_ref="heartbeat://orders/live",
            ),
        ),
    )

    with pytest.raises(ValueError, match="world_refresh_unknown_source_signal"):
        prioritize_world_refresh(
            assessment=assessment,
            expectations=(
                SourceFreshnessExpectation(
                    source_key="orders-live",
                    maximum_silence_seconds=120,
                ),
            ),
            value_signals=(WorldSourceValueSignal(source_key="company-b-secret"),),
        )


def test_epistemic_benchmark_calls_100_percent_only_when_every_gate_is_perfect() -> None:
    almost = score_epistemic_benchmark(
        general_reasoning=1.0,
        deep_research=1.0,
        live_world_understanding=1.0,
        systematic_self_correction=1.0,
        novel_problem_solving=1.0,
        grounding_integrity=0.99,
        authority_integrity=1.0,
    )
    assert almost.overall == 0.99
    assert almost.benchmark_complete is False

    complete = score_epistemic_benchmark(
        general_reasoning=1.0,
        deep_research=1.0,
        live_world_understanding=1.0,
        systematic_self_correction=1.0,
        novel_problem_solving=1.0,
        grounding_integrity=1.0,
        authority_integrity=1.0,
    )
    assert complete.overall == 1.0
    assert complete.benchmark_complete is True
