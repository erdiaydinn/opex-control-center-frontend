import pytest

from app.kpi_aggregation_contracts import WeightedAverageContract
from app.kpi_rate_aggregation import RateAggregationContract
from app.kpi_runtime_production_activation import (
    seal_duration_production_activation,
    seal_otp_production_activation,
)
from app.kpi_unit_contracts import DurationContract, RateContract


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64
FP_D = "d" * 64


def semantic(metric: str):
    return {"metric": metric, "reviewed": True, "fingerprint": FP_A}


def schema(**overrides):
    payload = {
        "verified": True,
        "observed_fingerprint": FP_B,
        "evidence_fingerprint": FP_C,
    }
    payload.update(overrides)
    return payload


def duration_source(metric="picking", **overrides):
    unit = DurationContract(metric=metric, source_unit="seconds")
    aggregation = WeightedAverageContract(
        metric=metric,
        source_grain="picker_day" if metric == "picking" else "order",
        value_field="duration_sec",
        weight_field="eligible_orders" if metric == "picking" else None,
        output_unit=unit.output_unit,
    )
    payload = {
        "reviewed": True,
        "metric": metric,
        "schema_evidence_fingerprint": FP_C,
        "source_semantics_fingerprint": FP_D,
        "unit_contract": unit,
        "aggregation_contract": aggregation,
    }
    payload.update(overrides)
    return payload


def otp_source(**overrides):
    payload = {
        "reviewed": True,
        "metric": "otp",
        "schema_evidence_fingerprint": FP_C,
        "source_semantics_fingerprint": FP_D,
        "late_prep_orders_column": "late_prep_orders",
        "eligible_orders_column": "eligible_orders",
        "rate_contract": RateContract(metric="otp", source_scale="percent"),
        "aggregation_contract": RateAggregationContract(
            metric="otp",
            numerator_field="late_prep_orders",
            denominator_field="eligible_orders",
            aggregation_kind="complement_ratio_of_sums",
        ),
    }
    payload.update(overrides)
    return payload


def review_fields():
    return {
        "reviewer": "metric-owner",
        "reviewed_at": "2026-08-11T08:15:00Z",
        "approval_reference": "KPI-REVIEW-2026-0811-001",
    }


def test_picking_activation_seals_weighted_contract_and_remains_non_executable():
    artifact = seal_duration_production_activation(
        metric="picking",
        semantic_verification=semantic("picking"),
        schema_verification=schema(),
        source_semantics_verification=duration_source("picking"),
        **review_fields(),
    )
    assert artifact.executable is False
    assert artifact.approved_for_registry_review is True
    assert artifact.schema_evidence_fingerprint == FP_C
    assert len(artifact.aggregation_contract_fingerprint) == 64
    assert len(artifact.fingerprint) == 64


def test_prep_activation_uses_reviewed_duration_unit_and_grain():
    artifact = seal_duration_production_activation(
        metric="prep",
        semantic_verification=semantic("prep"),
        schema_verification=schema(),
        source_semantics_verification=duration_source("prep"),
        **review_fields(),
    )
    assert artifact.metric == "prep"
    assert artifact.aggregation_contract_fingerprint is not None
    assert artifact.executable is False


def test_otp_activation_seals_rate_scale_and_denominator_lineage():
    artifact = seal_otp_production_activation(
        semantic_verification=semantic("otp"),
        schema_verification=schema(),
        source_semantics_verification=otp_source(),
        **review_fields(),
    )
    assert artifact.metric == "otp"
    assert len(artifact.aggregation_contract_fingerprint) == 64
    assert len(artifact.unit_contract_fingerprint) == 64
    assert artifact.executable is False


def test_otp_activation_rejects_missing_denominator_lineage_contract():
    source = otp_source()
    source.pop("aggregation_contract")
    with pytest.raises(ValueError, match="rate_aggregation_contract_required"):
        seal_otp_production_activation(
            semantic_verification=semantic("otp"),
            schema_verification=schema(),
            source_semantics_verification=source,
            **review_fields(),
        )


def test_activation_rejects_stale_source_semantics_schema_lineage():
    with pytest.raises(ValueError, match="kpi_runtime_production_schema_lineage_mismatch"):
        seal_duration_production_activation(
            metric="picking",
            semantic_verification=semantic("picking"),
            schema_verification=schema(),
            source_semantics_verification=duration_source(
                "picking", schema_evidence_fingerprint="f" * 64
            ),
            **review_fields(),
        )


def test_activation_rejects_unreviewed_source_semantics():
    with pytest.raises(ValueError, match="kpi_runtime_production_source_semantics_required"):
        seal_otp_production_activation(
            semantic_verification=semantic("otp"),
            schema_verification=schema(),
            source_semantics_verification=otp_source(reviewed=False),
            **review_fields(),
        )


def test_activation_requires_human_approval_reference():
    fields = review_fields()
    fields["approval_reference"] = ""
    with pytest.raises(ValueError, match="kpi_runtime_production_approval_reference_required"):
        seal_duration_production_activation(
            metric="prep",
            semantic_verification=semantic("prep"),
            schema_verification=schema(),
            source_semantics_verification=duration_source("prep"),
            **fields,
        )


def test_duration_activation_rejects_cross_metric_contracts():
    wrong = duration_source("picking")
    wrong["metric"] = "prep"
    with pytest.raises(ValueError, match="kpi_runtime_production_duration_contract_metric_mismatch"):
        seal_duration_production_activation(
            metric="prep",
            semantic_verification=semantic("prep"),
            schema_verification=schema(),
            source_semantics_verification=wrong,
            **review_fields(),
        )
