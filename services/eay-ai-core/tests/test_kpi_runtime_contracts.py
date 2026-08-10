import pytest

from app.kpi_aggregation_contracts import WeightedAverageContract
from app.kpi_runtime_contracts import (
    DURATION_RUNTIME_CONTRACTS,
    RATE_RUNTIME_CONTRACTS,
    DurationRuntimeContract,
    verify_kpi_runtime_activation,
)
from app.kpi_unit_contracts import DurationContract, RateContract


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64


def semantic(metric):
    return {"metric": metric, "reviewed": True, "fingerprint": FP_A}


def schema():
    return {
        "verified": True,
        "observed_fingerprint": FP_B,
        "evidence_fingerprint": FP_C,
    }


def test_duration_metric_fails_closed_without_runtime_contract():
    with pytest.raises(ValueError, match="kpi_runtime_contract_required:picking"):
        verify_kpi_runtime_activation(
            metric="picking",
            semantic_verification=semantic("picking"),
            schema_verification=schema(),
        )


def test_rate_metric_fails_closed_without_runtime_contract():
    with pytest.raises(ValueError, match="kpi_runtime_contract_required:otp"):
        verify_kpi_runtime_activation(
            metric="otp",
            semantic_verification=semantic("otp"),
            schema_verification=schema(),
        )


def test_picking_runtime_bundle_binds_unit_aggregation_and_evidence(monkeypatch):
    monkeypatch.setitem(
        DURATION_RUNTIME_CONTRACTS,
        "picking",
        DurationRuntimeContract(
            unit=DurationContract(metric="picking", source_unit="seconds"),
            aggregation=WeightedAverageContract(
                metric="picking",
                source_grain="picker_day",
                value_field="picking_time_sec",
                weight_field="eligible_orders",
                output_unit="seconds_per_order",
            ),
        ),
    )
    result = verify_kpi_runtime_activation(
        metric="picking",
        semantic_verification=semantic("picking"),
        schema_verification=schema(),
    )
    assert result["schema_evidence_fingerprint"] == FP_C
    assert len(result["unit_contract_fingerprint"]) == 64
    assert len(result["aggregation_contract_fingerprint"]) == 64


def test_otp_runtime_bundle_requires_explicit_scale(monkeypatch):
    monkeypatch.setitem(
        RATE_RUNTIME_CONTRACTS,
        "otp",
        RateContract(metric="otp", source_scale="fraction"),
    )
    result = verify_kpi_runtime_activation(
        metric="otp",
        semantic_verification=semantic("otp"),
        schema_verification=schema(),
    )
    assert result["aggregation_contract_fingerprint"] is None
    assert len(result["unit_contract_fingerprint"]) == 64


def test_non_unit_sensitive_metric_needs_no_runtime_bundle():
    assert (
        verify_kpi_runtime_activation(
            metric="orders",
            semantic_verification=semantic("orders"),
            schema_verification=schema(),
        )
        is None
    )
