from app.counterfactual_intelligence import (
    CounterfactualInput,
    CounterfactualStatus,
    evaluate_counterfactual,
)


def _payload(**updates) -> CounterfactualInput:
    base = dict(
        metric_name="orders",
        affected_scope="Istanbul marathon affected depots",
        control_scope="matched unaffected depots",
        affected_before=10_000,
        affected_during=7_100,
        control_before=10_000,
        control_during=9_700,
        affected_provenance_ref="ops://orders/istanbul/affected",
        control_provenance_ref="ops://orders/istanbul/control",
    )
    base.update(updates)
    return CounterfactualInput(**base)


def test_marathon_pattern_is_strengthened_when_control_remains_near_baseline():
    result = evaluate_counterfactual(_payload())

    assert result.status is CounterfactualStatus.SUPPORTS_HYPOTHESIS
    assert result.affected_change_pct == -29.0
    assert result.control_change_pct == -3.0
    assert result.effect_pct_vs_affected_baseline == -26.0
    assert result.causality_proven is False


def test_common_market_drop_weakens_event_specific_hypothesis():
    result = evaluate_counterfactual(
        _payload(control_during=7_300)
    )

    assert result.status is CounterfactualStatus.INSUFFICIENT
    assert result.effect_pct_vs_affected_baseline == -2.0
    assert "counterfactual_effect_not_material" in result.blockers


def test_unstable_control_scope_cannot_create_strong_counterfactual_support():
    result = evaluate_counterfactual(
        _payload(control_during=8_000)
    )

    assert result.status is CounterfactualStatus.WEAK_SIGNAL
    assert "control_scope_is_not_stable" in result.warnings
    assert result.causality_proven is False


def test_zero_baseline_fails_closed_instead_of_inventing_percentage():
    result = evaluate_counterfactual(
        _payload(affected_before=0, affected_during=100)
    )

    assert result.status is CounterfactualStatus.INSUFFICIENT
    assert result.affected_change_pct is None
    assert result.effect_pct_vs_affected_baseline is None
    assert "affected_baseline_zero" in result.blockers
