from datetime import datetime, timedelta, timezone

from app.context_intelligence import ContextKind, ContextSourceClass
from app.decision_intelligence import (
    DecisionPacketInput,
    DecisionReadiness,
    build_decision_packet,
)
from app.hypothesis_intelligence import (
    EvidenceDirection,
    HypothesisCandidate,
    HypothesisEvidence,
    rank_hypotheses,
)
from app.proactive_intelligence import (
    ExecutiveSignal,
    GovernedActionProposal,
    build_risk_radar,
)
from app.source_governance import SourceEvidence, evaluate_source_evidence

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 0, 0, tzinfo=UTC)


def _trusted_weather_report():
    evidence = SourceEvidence(
        evidence_id="weather",
        kind=ContextKind.WEATHER,
        claim_key="rain",
        claim_value="heavy",
        observed_at=NOW - timedelta(minutes=20),
        fetched_at=NOW - timedelta(minutes=10),
        source_name="weather",
        source_url="https://weather.example/istanbul",
        source_class=ContextSourceClass.VERIFIED_PROVIDER,
        source_confidence=0.92,
    )
    return evaluate_source_evidence([evidence], now=NOW, kind=ContextKind.WEATHER)


def _radar():
    return build_risk_radar(
        [
            ExecutiveSignal(
                signal_id="orders-drop",
                domain="operations",
                metric_name="orders",
                location="Istanbul",
                deviation_pct=-35.0,
                evidence_confidence=0.90,
                freshness_confidence=0.95,
                financial_materiality=0.80,
                time_to_impact_hours=1.0,
                provenance_refs=("ops://orders",),
            )
        ]
    )


def _ranking(with_counterevidence: bool = True):
    evidence = [
        HypothesisEvidence(
            evidence_ref="weather://rain",
            direction=EvidenceDirection.SUPPORT,
            weight=0.95,
            source_quality=0.95,
            independent_source_key="weather",
        ),
        HypothesisEvidence(
            evidence_ref="ops://orders",
            direction=EvidenceDirection.SUPPORT,
            weight=0.90,
            source_quality=0.95,
            independent_source_key="orders",
        ),
        HypothesisEvidence(
            evidence_ref="cf://control",
            direction=EvidenceDirection.SUPPORT,
            weight=0.90,
            source_quality=0.95,
            independent_source_key="control",
        ),
    ]
    if with_counterevidence:
        evidence.append(
            HypothesisEvidence(
                evidence_ref="ops://promo",
                direction=EvidenceDirection.REFUTE,
                weight=0.10,
                source_quality=0.95,
                independent_source_key="promo",
            )
        )
    return rank_hypotheses(
        [
            HypothesisCandidate(
                hypothesis_id="rain",
                label="Rain contributed to demand shift",
                evidence=tuple(evidence),
            )
        ]
    )


def test_decision_packet_can_prepare_safe_internal_action_without_external_execution():
    packet = build_decision_packet(
        DecisionPacketInput(
            decision_id="istanbul-rain",
            source_reports=(_trusted_weather_report(),),
            hypothesis_ranking=_ranking(),
            risk_radar=_radar(),
            actions=(
                GovernedActionProposal(
                    action_id="simulate-roster",
                    description="Simulate staffing alternatives",
                ),
            ),
        )
    )

    assert packet.readiness in {DecisionReadiness.PREPARE, DecisionReadiness.ESCALATE}
    assert "simulate-roster" in packet.safe_prepare_action_ids
    assert packet.automatic_external_execution_allowed is False


def test_unresolved_hypothesis_forces_investigation_instead_of_action_confidence():
    packet = build_decision_packet(
        DecisionPacketInput(
            decision_id="rain-unresolved",
            source_reports=(_trusted_weather_report(),),
            hypothesis_ranking=_ranking(with_counterevidence=False),
            risk_radar=_radar(),
        )
    )

    assert packet.readiness is DecisionReadiness.INVESTIGATE
    assert packet.confidence_cap <= 0.60
    assert "hypothesis_requires_more_evidence" in packet.blockers


def test_external_action_remains_approval_gated():
    packet = build_decision_packet(
        DecisionPacketInput(
            decision_id="partner-message",
            source_reports=(_trusted_weather_report(),),
            hypothesis_ranking=_ranking(),
            risk_radar=_radar(),
            actions=(
                GovernedActionProposal(
                    action_id="send-partner-message",
                    description="Send external partner notification",
                    external_side_effect=True,
                    required_permission="partner.notify",
                    requires_human_approval=True,
                ),
            ),
        )
    )

    assert "send-partner-message" in packet.approval_gated_action_ids
    assert packet.human_review_required is True
    assert packet.automatic_external_execution_allowed is False
