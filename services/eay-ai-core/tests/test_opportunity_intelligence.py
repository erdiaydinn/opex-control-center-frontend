from app.opportunity_intelligence import (
    OpportunityDisposition,
    OpportunitySignal,
    assess_opportunity,
)


def _signal(**updates):
    base = dict(
        opportunity_id="rain-demand",
        domain="retail_operations",
        location="Istanbul",
        expected_uplift_pct=18.0,
        evidence_confidence=0.90,
        freshness_confidence=0.95,
        capacity_headroom_pct=25.0,
        inventory_readiness=0.90,
        margin_quality=0.80,
        time_to_impact_hours=6.0,
        provenance_refs=("weather://rain", "ops://baseline"),
    )
    base.update(updates)
    return OpportunitySignal(**base)


def test_evidence_backed_demand_uplift_with_headroom_is_prioritized_or_prepared():
    result = assess_opportunity(_signal())

    assert result.disposition in {OpportunityDisposition.PREPARE, OpportunityDisposition.PRIORITIZE}
    assert result.evidence_quality == 0.90
    assert "simulate_workforce_and_delivery_capacity" in result.suggested_preparations
    assert "review_inventory_and_availability" in result.suggested_preparations


def test_upside_without_capacity_is_not_blindly_prioritized():
    result = assess_opportunity(
        _signal(capacity_headroom_pct=4.0)
    )

    assert result.disposition is not OpportunityDisposition.PRIORITIZE
    assert "capacity_headroom_insufficient_for_expected_uplift" in result.blockers


def test_low_inventory_readiness_turns_opportunity_into_preparation_work():
    result = assess_opportunity(
        _signal(inventory_readiness=0.30)
    )

    assert "inventory_readiness_low" in result.blockers
    assert "review_inventory_and_availability" in result.suggested_preparations


def test_low_confidence_opportunity_is_not_high_priority_even_with_large_uplift():
    result = assess_opportunity(
        _signal(
            expected_uplift_pct=40.0,
            capacity_headroom_pct=60.0,
            evidence_confidence=0.35,
            freshness_confidence=0.40,
        )
    )

    assert result.disposition in {OpportunityDisposition.IGNORE, OpportunityDisposition.WATCH}
    assert "opportunity_evidence_quality_low" in result.blockers
