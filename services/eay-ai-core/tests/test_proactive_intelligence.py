import pytest

from app.proactive_intelligence import (
    ExecutiveSignal,
    GovernedActionProposal,
    RadarDisposition,
    RiskLevel,
    build_risk_radar,
    score_executive_signal,
)


def _signal(signal_id: str, **updates) -> ExecutiveSignal:
    base = dict(
        signal_id=signal_id,
        domain="operations",
        metric_name="orders",
        location="Istanbul",
        deviation_pct=-29.0,
        evidence_confidence=0.92,
        freshness_confidence=0.95,
        financial_materiality=0.65,
        legal_severity=0.0,
        safety_severity=0.0,
        time_to_impact_hours=2.0,
        provenance_refs=(f"ops://evidence/{signal_id}",),
    )
    base.update(updates)
    return ExecutiveSignal(**base)


def test_material_fresh_signal_is_surfaced_or_escalated():
    item = score_executive_signal(_signal("orders-drop"))

    assert item.priority_score >= 0.45
    assert item.disposition in {RadarDisposition.SURFACE, RadarDisposition.ESCALATE}
    assert item.provenance_refs == ("ops://evidence/orders-drop",)


def test_stale_low_confidence_signal_is_suppressed_from_attention():
    item = score_executive_signal(
        _signal(
            "stale-rumor",
            evidence_confidence=0.30,
            freshness_confidence=0.20,
            deviation_pct=-50.0,
            financial_materiality=1.0,
        )
    )

    assert item.disposition is RadarDisposition.SUPPRESS
    assert "stale_or_low_freshness_signal" in item.warnings
    assert "low_evidence_confidence" in item.warnings


def test_duplicate_metric_location_signals_are_deduplicated_to_highest_priority():
    radar = build_risk_radar(
        [
            _signal("older", evidence_confidence=0.60, freshness_confidence=0.60),
            _signal("better", evidence_confidence=0.95, freshness_confidence=0.95),
        ]
    )

    assert [item.signal_id for item in radar.items] == ["better"]
    assert radar.suppressed_duplicate_signal_ids == ("older",)


def test_cross_domain_cluster_receives_cascade_boost():
    radar = build_risk_radar(
        [
            _signal("orders", domain="operations", metric_name="orders"),
            _signal("riders", domain="workforce", metric_name="rider_capacity", deviation_pct=-22.0),
            _signal("margin", domain="finance", metric_name="contribution_margin", deviation_pct=-18.0),
        ]
    )

    assert len(radar.items) == 3
    assert all(item.cascade_cluster for item in radar.items)
    assert all("cross_domain_cascade_cluster" in item.warnings for item in radar.items)


def test_severe_legal_signal_requires_human_review():
    item = score_executive_signal(
        _signal(
            "legal-risk",
            domain="legal",
            metric_name="regulatory_exposure",
            deviation_pct=10.0,
            legal_severity=0.95,
            financial_materiality=0.2,
        )
    )

    assert item.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    assert item.requires_human_review is True


def test_external_side_effect_action_cannot_bypass_human_approval():
    with pytest.raises(ValueError, match="side_effect_or_irreversible_action_requires_human_approval"):
        GovernedActionProposal(
            action_id="close-store",
            description="Close a store externally",
            reversible=False,
            external_side_effect=True,
            irreversible=False,
            required_permission="store.close",
            requires_human_approval=False,
        )


def test_external_action_requires_explicit_permission_even_with_approval():
    with pytest.raises(ValueError, match="external_action_permission_required"):
        GovernedActionProposal(
            action_id="notify-partner",
            description="Notify an external partner",
            external_side_effect=True,
            requires_human_approval=True,
        )
