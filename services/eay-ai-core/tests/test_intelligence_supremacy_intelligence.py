from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.decision_intelligence import DecisionReadiness, ExecutiveDecisionPacket
from app.hypothesis_intelligence import HypothesisAssessment, HypothesisRanking
from app.intelligence_supremacy import (
    ActiveLearningCalibration,
    InvestigationCandidate,
    InvestigationKind,
    LearningCalibrationApproval,
    ReasoningMode,
    ReasoningRisk,
    activate_learning_calibration,
    build_intelligence_cycle,
    build_learning_calibration_candidate,
    identify_knowledge_gaps,
    plan_information_gain,
    select_reasoning_strength,
)
from app.outcome_learning import AttributionStrength, DecisionOutcomeAssessment
from app.world_model import (
    EntityKind,
    TruthClass,
    WorldAssertion,
    WorldEntity,
    build_world_snapshot,
)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
TENANT = "tenant://ys-tr"


def _world(*, contradiction: bool = False):
    entity = WorldEntity(
        entity_id="warehouse://fulya",
        tenant_id=TENANT,
        kind=EntityKind.WAREHOUSE,
        display_name="Fulya",
    )
    assertions = [
        WorldAssertion(
            assertion_id="assertion://orders-a",
            tenant_id=TENANT,
            entity_id=entity.entity_id,
            field_name="orders",
            value=100,
            truth_class=TruthClass.VERIFIED_COMPANY,
            valid_from=NOW,
            observed_at=NOW,
            source_ref="source://company-a",
            evidence_ref="evidence://orders-a",
            confidence=0.95,
        )
    ]
    if contradiction:
        assertions.append(
            WorldAssertion(
                assertion_id="assertion://orders-b",
                tenant_id=TENANT,
                entity_id=entity.entity_id,
                field_name="orders",
                value=120,
                truth_class=TruthClass.VERIFIED_COMPANY,
                valid_from=NOW,
                observed_at=NOW,
                source_ref="source://company-b",
                evidence_ref="evidence://orders-b",
                confidence=0.95,
            )
        )
    return build_world_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=[entity],
        assertions=assertions,
    )


def _ranking(*, ambiguous: bool = True):
    assessments = (
        HypothesisAssessment(
            hypothesis_id="hypothesis://weather",
            label="Weather pressure",
            score=0.4,
            confidence=0.55 if ambiguous else 0.8,
            support_weight=1.0,
            refute_weight=0.4,
            independent_source_count=2,
            counterevidence_present=True,
        ),
        HypothesisAssessment(
            hypothesis_id="hypothesis://staffing",
            label="Staffing pressure",
            score=0.3,
            confidence=0.50 if ambiguous else 0.4,
            support_weight=0.9,
            refute_weight=0.5,
            independent_source_count=2,
            counterevidence_present=True,
        ),
    )
    return HypothesisRanking(
        assessments=assessments,
        leading_hypothesis_id=assessments[0].hypothesis_id,
        leading_margin=0.05 if ambiguous else 0.4,
        decisive=not ambiguous,
        requires_more_evidence=ambiguous,
        blockers=("competing_hypotheses_too_close",) if ambiguous else (),
    )


def _decision(*, readiness=DecisionReadiness.INVESTIGATE, blockers=()):
    return ExecutiveDecisionPacket(
        decision_id="decision://fulya-demand",
        readiness=readiness,
        confidence_cap=0.6,
        automatic_external_execution_allowed=False,
        human_review_required=False,
        blockers=blockers,
        firm_company_claim_authorized=False,
    )


def test_information_gain_prefers_test_that_resolves_world_and_hypothesis_uncertainty():
    world = _world(contradiction=True)
    decision = _decision(blockers=("hypothesis_requires_more_evidence",))
    ranking = _ranking(ambiguous=True)
    gaps = identify_knowledge_gaps(world=world, hypotheses=ranking, decision=decision)
    gap_ids = {item.gap_id for item in gaps}
    world_gap = next(item for item in gap_ids if item.startswith("world:"))
    hypothesis_gap = "hypothesis:ranking-ambiguous"

    broad = InvestigationCandidate(
        investigation_id="investigation://company-and-weather",
        kind=InvestigationKind.COMPANY_READ,
        resolves_gap_ids=(world_gap, hypothesis_gap),
        discriminates_hypothesis_ids=(
            "hypothesis://weather",
            "hypothesis://staffing",
        ),
        expected_signal_quality=0.9,
        independent_source_gain=0.8,
        estimated_latency_ms=500,
        estimated_cost_units=10.0,
        evidence_ref="evidence://reviewed-read-plan",
    )
    narrow = InvestigationCandidate(
        investigation_id="investigation://cheap-world-read",
        kind=InvestigationKind.COMPANY_READ,
        resolves_gap_ids=(world_gap,),
        expected_signal_quality=0.6,
        independent_source_gain=0.2,
        estimated_latency_ms=10,
        estimated_cost_units=0.0,
        evidence_ref="evidence://cheap-read-plan",
    )

    plan = plan_information_gain(
        gaps=gaps,
        investigations=(narrow, broad),
        maximum_investigations=1,
        maximum_cost_units=20.0,
    )

    assert plan.ranked[0].investigation_id == broad.investigation_id
    assert plan.selected_investigation_ids == (broad.investigation_id,)
    assert world_gap not in plan.unresolved_gap_ids
    assert hypothesis_gap not in plan.unresolved_gap_ids
    assert plan.automatic_execution_allowed is False
    assert plan.paid_frontier_authority_granted is False


def test_missing_live_truth_forces_investigate_before_stronger_model():
    world = _world()
    decision = _decision(
        readiness=DecisionReadiness.HOLD,
        blockers=("live_company_truth_receipt_missing",),
    )
    gaps = identify_knowledge_gaps(world=world, hypotheses=None, decision=decision)
    live_gap = next(
        item.gap_id
        for item in gaps
        if item.gap_id.startswith("decision:live_company_")
    )
    read = InvestigationCandidate(
        investigation_id="investigation://authorized-live-read",
        kind=InvestigationKind.COMPANY_READ,
        resolves_gap_ids=(live_gap,),
        expected_signal_quality=1.0,
        independent_source_gain=1.0,
        estimated_latency_ms=100,
        estimated_cost_units=1.0,
        evidence_ref="evidence://live-read-contract",
    )
    info = plan_information_gain(gaps=gaps, investigations=(read,))
    reasoning = select_reasoning_strength(
        risk=ReasoningRisk.CRITICAL,
        decision=decision,
        information_gain=info,
    )

    assert reasoning.mode is ReasoningMode.INVESTIGATE_FIRST
    assert reasoning.frontier_escalation_candidate is False
    assert reasoning.paid_frontier_authority_granted is False
    assert "reasoning_cannot_substitute_for_missing_live_company_truth" in reasoning.blockers


def test_critical_decision_can_request_council_and_frontier_but_never_authorize_spend():
    decision = _decision(readiness=DecisionReadiness.PREPARE)
    info = plan_information_gain(gaps=(), investigations=())
    reasoning = select_reasoning_strength(
        risk=ReasoningRisk.CRITICAL,
        decision=decision,
        information_gain=info,
    )

    assert reasoning.mode is ReasoningMode.HUMAN_REVIEW
    assert reasoning.local_council_required is True
    assert reasoning.frontier_escalation_candidate is True
    assert reasoning.requires_platform_admin_paid_grant is True
    assert reasoning.human_review_required is True
    assert reasoning.paid_frontier_authority_granted is False
    assert reasoning.execution_authority_granted is False


def test_information_gain_rejects_mutating_probe():
    with pytest.raises(ValidationError, match="information_gain_investigation_must_be_read_only"):
        InvestigationCandidate(
            investigation_id="investigation://write-probe",
            kind=InvestigationKind.COMPANY_READ,
            resolves_gap_ids=("decision:gap",),
            expected_signal_quality=1.0,
            independent_source_gain=1.0,
            estimated_latency_ms=100,
            estimated_cost_units=1.0,
            evidence_ref="evidence://bad-probe",
            read_only=False,
            external_side_effect=True,
        )


def test_outcome_feedback_is_review_gated_and_tamper_evident():
    assessment = DecisionOutcomeAssessment(
        decision_id="decision://fulya-demand",
        tenant_id=TENANT,
        metric_results=(),
        mean_absolute_error=None,
        direction_accuracy=None,
        attribution_strength=AttributionStrength.NONE,
        learning_evidence_refs=("evidence://observed-outcome",),
        suggested_confidence_multiplier=0.7,
        blockers=("outcome_learning_metric_missing:orders",),
    )
    candidate = build_learning_calibration_candidate(
        assessment=assessment,
        decision_type="ops.demand",
        recorded_at=NOW,
    )

    assert candidate.active is False
    assert candidate.automatic_model_weight_update_allowed is False
    assert candidate.automatic_policy_update_allowed is False

    tampered = candidate.model_copy(update={"proposed_confidence_multiplier": 1.2})
    approval = LearningCalibrationApproval(
        candidate_fingerprint=candidate.fingerprint,
        reviewer_ref="reviewer://evidence-colony",
        approval_evidence_ref="evidence://human-review",
        approved_at=NOW,
    )
    with pytest.raises(ValidationError, match="learning_calibration_candidate_fingerprint_mismatch"):
        activate_learning_calibration(candidate=tampered, approval=approval)

    active = activate_learning_calibration(candidate=candidate, approval=approval)
    assert isinstance(active, ActiveLearningCalibration)
    assert active.confidence_multiplier == 0.7
    assert active.model_weights_mutated is False
    assert active.business_policy_mutated is False


def test_closed_loop_calibration_increases_reasoning_strength_without_mutating_authority():
    world = _world()
    decision = _decision(readiness=DecisionReadiness.PREPARE)
    cycle = build_intelligence_cycle(
        world=world,
        hypotheses=_ranking(ambiguous=False),
        decision=decision,
        investigations=(),
        risk=ReasoningRisk.MEDIUM,
        calibrated_confidence_multiplier=0.7,
    )

    assert cycle.reasoning.mode is ReasoningMode.LOCAL_COUNCIL
    assert cycle.reasoning.frontier_escalation_candidate is True
    assert cycle.reasoning.requires_platform_admin_paid_grant is True
    assert cycle.reasoning.paid_frontier_authority_granted is False
    assert cycle.reasoning.execution_authority_granted is False
    assert cycle.production_truth_promoted is False

    tampered = cycle.model_copy(update={"firm_company_claim_authorized": True})
    with pytest.raises(ValidationError, match="intelligence_cycle_fingerprint_mismatch"):
        type(cycle).model_validate(tampered.model_dump(mode="json"))
