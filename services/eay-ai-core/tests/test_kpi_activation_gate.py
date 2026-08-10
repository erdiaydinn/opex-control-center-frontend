import pytest

from app.kpi_activation_gate import verify_duration_kpi_activation
from app.kpi_aggregation_contracts import WeightedAverageContract
from app.kpi_unit_contracts import DurationContract


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64


def semantic(metric="picking"):
    return {"metric": metric, "reviewed": True, "fingerprint": FP_A}


def schema(*, verified=True, evidence=True):
    return {
        "verified": verified,
        "observed_fingerprint": FP_B,
        "evidence_fingerprint": FP_C if evidence else None,
    }


def aggregation(**kwargs):
    data = dict(
        metric="picking",
        source_grain="picker_day",
        value_field="picking_time_min",
        weight_field="eligible_orders",
        output_unit="seconds_per_order",
    )
    data.update(kwargs)
    return WeightedAverageContract(**data)


def test_picking_activation_requires_all_contracts_to_agree():
    unit = DurationContract(metric="picking", source_unit="minutes")
    agg = aggregation()
    result = verify_duration_kpi_activation(
        metric="picking",
        semantic_verification=semantic(),
        schema_verification=schema(),
        unit_contract=unit,
        aggregation_contract=agg,
    )
    assert result.metric == "picking"
    assert result.semantic_fingerprint == FP_A
    assert result.schema_fingerprint == FP_B
    assert result.schema_evidence_fingerprint == FP_C
    assert result.unit_contract_fingerprint == unit.fingerprint
    assert result.aggregation_contract_fingerprint == agg.fingerprint


def test_picking_activation_rejects_unweighted_picker_day_contract():
    with pytest.raises(ValueError, match="aggregation_weight_required_for_picker_day"):
        verify_duration_kpi_activation(
            metric="picking",
            semantic_verification=semantic(),
            schema_verification=schema(),
            unit_contract=DurationContract(metric="picking", source_unit="minutes"),
            aggregation_contract=aggregation(weight_field=None),
        )


def test_picking_activation_rejects_unit_metric_mismatch():
    with pytest.raises(ValueError, match="kpi_activation_unit_metric_mismatch"):
        verify_duration_kpi_activation(
            metric="picking",
            semantic_verification=semantic(),
            schema_verification=schema(),
            unit_contract=DurationContract(metric="prep", source_unit="minutes"),
            aggregation_contract=aggregation(),
        )


def test_picking_activation_rejects_aggregation_metric_mismatch():
    with pytest.raises(ValueError, match="kpi_activation_aggregation_metric_mismatch"):
        verify_duration_kpi_activation(
            metric="picking",
            semantic_verification=semantic(),
            schema_verification=schema(),
            unit_contract=DurationContract(metric="picking", source_unit="minutes"),
            aggregation_contract=aggregation(metric="prep"),
        )


def test_picking_activation_rejects_output_unit_mismatch():
    with pytest.raises(ValueError, match="kpi_activation_output_unit_mismatch"):
        verify_duration_kpi_activation(
            metric="picking",
            semantic_verification=semantic(),
            schema_verification=schema(),
            unit_contract=DurationContract(metric="picking", source_unit="minutes"),
            aggregation_contract=aggregation(output_unit="minutes_per_order"),
        )


def test_picking_activation_requires_live_schema_verification():
    with pytest.raises(ValueError, match="kpi_activation_schema_verification_required"):
        verify_duration_kpi_activation(
            metric="picking",
            semantic_verification=semantic(),
            schema_verification=schema(verified=False),
            unit_contract=DurationContract(metric="picking", source_unit="minutes"),
            aggregation_contract=aggregation(),
        )


def test_picking_activation_rejects_non_sha256_provenance():
    bad_semantic = semantic()
    bad_semantic["fingerprint"] = "not-a-sha"
    with pytest.raises(ValueError, match="kpi_activation_invalid_fingerprint:semantic"):
        verify_duration_kpi_activation(
            metric="picking",
            semantic_verification=bad_semantic,
            schema_verification=schema(),
            unit_contract=DurationContract(metric="picking", source_unit="minutes"),
            aggregation_contract=aggregation(),
        )
