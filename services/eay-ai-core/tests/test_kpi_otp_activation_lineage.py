import pytest

from app.kpi_rate_aggregation import RateAggregationContract
from app.kpi_runtime_production_activation import seal_otp_production_activation
from app.kpi_unit_contracts import RateContract


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64
FP_D = "d" * 64


def semantic():
    return {"metric": "otp", "reviewed": True, "fingerprint": FP_A}


def schema():
    return {
        "verified": True,
        "observed_fingerprint": FP_B,
        "evidence_fingerprint": FP_C,
    }


def source(aggregation=None, **overrides):
    payload = {
        "reviewed": True,
        "metric": "otp",
        "schema_evidence_fingerprint": FP_C,
        "source_semantics_fingerprint": FP_D,
        "late_prep_orders_column": "late_prep_orders",
        "eligible_orders_column": "eligible_orders",
        "rate_contract": RateContract(metric="otp", source_scale="percent"),
        "aggregation_contract": aggregation
        or RateAggregationContract(
            metric="otp",
            numerator_field="late_prep_orders",
            denominator_field="eligible_orders",
            aggregation_kind="complement_ratio_of_sums",
        ),
    }
    payload.update(overrides)
    return payload


def review():
    return {
        "reviewer": "metric-owner",
        "reviewed_at": "2026-08-11T08:15:00Z",
        "approval_reference": "KPI-REVIEW-2026-0811-OTP",
    }


def test_otp_activation_accepts_exact_reviewed_count_lineage():
    artifact = seal_otp_production_activation(
        semantic_verification=semantic(),
        schema_verification=schema(),
        source_semantics_verification=source(),
        **review(),
    )
    assert artifact.metric == "otp"
    assert artifact.executable is False


def test_otp_activation_requires_reviewed_lineage_columns():
    with pytest.raises(ValueError, match="otp_lineage_columns_required"):
        seal_otp_production_activation(
            semantic_verification=semantic(),
            schema_verification=schema(),
            source_semantics_verification=source(eligible_orders_column=""),
            **review(),
        )


def test_otp_activation_rejects_contract_mapped_to_different_columns():
    wrong = RateAggregationContract(
        metric="otp",
        numerator_field="other_late_orders",
        denominator_field="eligible_orders",
        aggregation_kind="complement_ratio_of_sums",
    )
    with pytest.raises(ValueError, match="otp_aggregation_lineage_mismatch"):
        seal_otp_production_activation(
            semantic_verification=semantic(),
            schema_verification=schema(),
            source_semantics_verification=source(aggregation=wrong),
            **review(),
        )


def test_otp_activation_rejects_non_complement_aggregation():
    wrong = RateAggregationContract(
        metric="otp",
        numerator_field="late_prep_orders",
        denominator_field="eligible_orders",
        aggregation_kind="ratio_of_sums",
    )
    with pytest.raises(ValueError, match="otp_aggregation_kind_mismatch"):
        seal_otp_production_activation(
            semantic_verification=semantic(),
            schema_verification=schema(),
            source_semantics_verification=source(aggregation=wrong),
            **review(),
        )
