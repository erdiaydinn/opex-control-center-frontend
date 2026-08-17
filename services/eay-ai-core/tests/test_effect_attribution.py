import pytest

from app.effect_attribution import (
    EffectDisposition,
    EffectRequestCandidate,
    StateTransitionObservation,
    attribute_effect,
)


def _transition():
    return StateTransitionObservation(
        transition_id="stock-27-to-24",
        tenant_id="warehouse:fulya",
        entity_ref="sku:1",
        field_name="stock_on_hand",
        before_value=27,
        after_value=24,
        verifier_ref="capability://inventory.read-stock",
        evidence_ref="evidence://stock-readback",
    )


def _candidate(request_ref="inventory-write", **overrides):
    payload = dict(
        request_ref=request_ref,
        method="POST",
        operation_ref="/inventory/adjustments",
        status_code=200,
        tenant_id="warehouse:fulya",
        request_field_names=("sku_id", "quantity", "reason"),
        response_field_names=("transaction_id", "stock_on_hand"),
        state_field_hints=("stock_on_hand",),
        independent_readback_matches=True,
        transaction_reference_observed=True,
        evidence_refs=(f"evidence://{request_ref}",),
    )
    payload.update(overrides)
    return EffectRequestCandidate(**payload)


def test_business_write_beats_telemetry_and_audit_side_channels():
    decision = attribute_effect(
        transition=_transition(),
        candidates=[
            _candidate(),
            _candidate(
                "analytics",
                operation_ref="/analytics/click",
                telemetry_like=True,
                independent_readback_matches=False,
                transaction_reference_observed=False,
                state_field_hints=(),
                response_field_names=(),
            ),
            _candidate(
                "audit",
                operation_ref="/audit/events",
                audit_like=True,
                independent_readback_matches=False,
                transaction_reference_observed=False,
                state_field_hints=(),
                response_field_names=(),
            ),
        ],
    )

    assert decision.disposition is EffectDisposition.CANDIDATE
    assert decision.selected_request_ref == "inventory-write"
    assert decision.causal_proof is False
    assert decision.direct_api_execution_allowed is False
    assert "effect_replay_equivalence_not_yet_verified" in decision.blockers


def test_close_candidates_fail_closed_as_ambiguous():
    decision = attribute_effect(
        transition=_transition(),
        candidates=[_candidate("one"), _candidate("two")],
    )

    assert decision.disposition is EffectDisposition.AMBIGUOUS
    assert decision.selected_request_ref is None
    assert "effect_attribution_ambiguous" in decision.blockers


def test_cross_tenant_candidate_is_not_considered():
    decision = attribute_effect(
        transition=_transition(),
        candidates=[_candidate(tenant_id="warehouse:besiktas")],
    )

    assert decision.disposition is EffectDisposition.INSUFFICIENT
    assert "effect_no_tenant_scoped_request_candidates" in decision.blockers


def test_no_state_change_is_not_an_effect_observation():
    with pytest.raises(ValueError, match="effect_transition_requires_state_change"):
        StateTransitionObservation(
            transition_id="no-change",
            tenant_id="warehouse:fulya",
            entity_ref="sku:1",
            field_name="stock_on_hand",
            before_value=27,
            after_value=27,
            verifier_ref="capability://inventory.read-stock",
            evidence_ref="evidence://same",
        )
