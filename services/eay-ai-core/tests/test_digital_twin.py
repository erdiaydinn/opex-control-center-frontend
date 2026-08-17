from datetime import datetime, timedelta, timezone

from app.digital_twin import (
    InterventionAssumption,
    InterventionKind,
    InterventionSpec,
    TwinMetricProjection,
    TwinScenario,
    TwinSimulationInput,
    simulate_intervention,
)
from app.world_model import EntityKind, TruthClass, WorldAssertion, WorldEntity, build_world_snapshot

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 3, 30, tzinfo=UTC)


def _snapshot(*, contradictory=False):
    entity = WorldEntity(
        entity_id="warehouse:fulya",
        tenant_id="warehouse:fulya",
        kind=EntityKind.WAREHOUSE,
        display_name="Fulya",
    )
    assertions = [
        WorldAssertion(
            assertion_id="capacity-a",
            tenant_id="warehouse:fulya",
            entity_id="warehouse:fulya",
            field_name="order_capacity_per_hour",
            value=100,
            truth_class=TruthClass.GOVERNED_OPERATIONAL,
            valid_from=NOW - timedelta(hours=1),
            observed_at=NOW - timedelta(minutes=5),
            source_ref="ops://capacity",
            evidence_ref="evidence://capacity-a",
            confidence=1.0,
        )
    ]
    if contradictory:
        assertions.append(
            WorldAssertion(
                assertion_id="capacity-b",
                tenant_id="warehouse:fulya",
                entity_id="warehouse:fulya",
                field_name="order_capacity_per_hour",
                value=90,
                truth_class=TruthClass.GOVERNED_OPERATIONAL,
                valid_from=NOW - timedelta(hours=1),
                observed_at=NOW - timedelta(minutes=4),
                source_ref="ops://capacity-2",
                evidence_ref="evidence://capacity-b",
                confidence=1.0,
            )
        )
    return build_world_snapshot(
        tenant_id="warehouse:fulya",
        as_of=NOW,
        entities=[entity],
        assertions=assertions,
    )


def _input():
    intervention = InterventionSpec(
        intervention_id="add-picker",
        kind=InterventionKind.STAFFING,
        target_entity_ids=("warehouse:fulya",),
        description="Add one picker for the peak window",
        required_baseline_field_keys=("warehouse:fulya:order_capacity_per_hour",),
        assumptions=(
            InterventionAssumption(
                assumption_id="productivity",
                statement="Added picker changes throughput within historical range",
                evidence_ref="evidence://historical-picker-productivity",
                confidence=0.82,
            ),
        ),
    )
    return TwinSimulationInput(
        intervention=intervention,
        scenarios=(
            TwinScenario(
                scenario_id="upside",
                label="Productivity holds",
                probability=0.6,
                financial_impact=1200.0,
                service_level_impact_pct=5.0,
                demand_impact_pct=0.0,
                projections=(
                    TwinMetricProjection(
                        metric_key="order_capacity_per_hour",
                        baseline_value=100,
                        projected_value=112,
                        unit="orders/hour",
                        method_ref="model://staffing-capacity-v1",
                        evidence_refs=("evidence://historical-picker-productivity",),
                    ),
                ),
                evidence_refs=("evidence://upside",),
            ),
            TwinScenario(
                scenario_id="downside",
                label="Training friction offsets benefit",
                probability=0.4,
                financial_impact=-300.0,
                service_level_impact_pct=-1.0,
                demand_impact_pct=0.0,
                projections=(
                    TwinMetricProjection(
                        metric_key="order_capacity_per_hour",
                        baseline_value=100,
                        projected_value=98,
                        unit="orders/hour",
                        method_ref="model://staffing-capacity-v1",
                        evidence_refs=("evidence://training-friction",),
                    ),
                ),
                evidence_refs=("evidence://downside",),
            ),
        ),
    )


def test_simulation_binds_to_world_snapshot_and_computes_weighted_impacts():
    snapshot = _snapshot()
    result = simulate_intervention(snapshot=snapshot, payload=_input())

    assert result.world_snapshot_fingerprint == snapshot.fingerprint
    assert result.expected_financial_impact == 600.0
    impact = result.expected_metric_impacts[0]
    assert impact.metric_key == "order_capacity_per_hour"
    assert impact.expected_projected_value == 106.4
    assert impact.expected_delta == 6.4
    assert result.execution_allowed is False
    assert result.forecast_truth_claimed is False
    assert result.counterfactual_only is True


def test_contradictory_world_state_blocks_decision_confidence():
    result = simulate_intervention(snapshot=_snapshot(contradictory=True), payload=_input())

    assert "digital_twin_baseline_field_contradictory:warehouse:fulya:order_capacity_per_hour" in result.blockers
    assert result.confidence_cap <= 0.40
    assert result.execution_allowed is False


def test_unknown_target_is_exposed_instead_of_simulated_silently():
    payload = _input()
    modified = payload.model_copy(
        update={
            "intervention": payload.intervention.model_copy(
                update={"target_entity_ids": ("warehouse:unknown",)}
            )
        }
    )
    result = simulate_intervention(snapshot=_snapshot(), payload=modified)

    assert "digital_twin_target_entity_missing:warehouse:unknown" in result.blockers
