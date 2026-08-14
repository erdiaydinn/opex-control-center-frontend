from datetime import date

import pytest

from app.kpi_aggregation_contracts import WeightedAverageContract
from app.kpi_putaway_sla import PutawaySlaContract
from app.kpi_rate_aggregation import RateAggregationContract
from app.kpi_runtime_contracts import (
    DURATION_RUNTIME_CONTRACTS,
    PUTAWAY_RUNTIME_CONTRACTS,
    RATE_RUNTIME_CONTRACTS,
    DurationRuntimeContract,
    PutawayRuntimeContract,
    RateRuntimeContract,
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


def putaway_sla(*, version="1", start=date(2026, 1, 1), end=None):
    return PutawaySlaContract(
        contract_id=f"ops.putaway.sla.{version}",
        version=version,
        effective_from=start,
        effective_to=end,
        schema_evidence_fingerprint=FP_C,
        reviewed=True,
        reviewer="ops-reviewer",
    )


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


def test_putaway_metric_fails_closed_without_runtime_contract():
    with pytest.raises(ValueError, match="kpi_runtime_contract_required:putaway"):
        verify_kpi_runtime_activation(
            metric="putaway",
            semantic_verification=semantic("putaway"),
            schema_verification=schema(),
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 10),
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


def test_otp_runtime_bundle_binds_scale_and_denominator_lineage(monkeypatch):
    monkeypatch.setitem(
        RATE_RUNTIME_CONTRACTS,
        "otp",
        RateRuntimeContract(
            unit=RateContract(metric="otp", source_scale="percent"),
            aggregation=RateAggregationContract(
                metric="otp",
                numerator_field="late_prep_orders",
                denominator_field="eligible_orders",
                aggregation_kind="complement_ratio_of_sums",
            ),
        ),
    )
    result = verify_kpi_runtime_activation(
        metric="otp",
        semantic_verification=semantic("otp"),
        schema_verification=schema(),
    )
    assert len(result["aggregation_contract_fingerprint"]) == 64
    assert len(result["unit_contract_fingerprint"]) == 64
    assert len(result["activation_provenance_fingerprint"]) == 64


def test_putaway_runtime_bundle_binds_temporal_sla_and_quantity(monkeypatch):
    monkeypatch.setitem(
        PUTAWAY_RUNTIME_CONTRACTS,
        "putaway",
        PutawayRuntimeContract(sla_contracts=(putaway_sla(),)),
    )
    result = verify_kpi_runtime_activation(
        metric="putaway",
        semantic_verification=semantic("putaway"),
        schema_verification=schema(),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 10),
    )
    assert len(result["sla_contract_fingerprint"]) == 64
    assert len(result["quantity_contract_fingerprint"]) == 64
    assert len(result["activation_provenance_fingerprint"]) == 64


def test_putaway_runtime_rejects_query_spanning_sla_versions(monkeypatch):
    monkeypatch.setitem(
        PUTAWAY_RUNTIME_CONTRACTS,
        "putaway",
        PutawayRuntimeContract(
            sla_contracts=(
                putaway_sla(version="1", start=date(2026, 1, 1), end=date(2026, 7, 31)),
                putaway_sla(version="2", start=date(2026, 8, 1), end=None),
            )
        ),
    )
    with pytest.raises(ValueError, match="spans_sla_versions"):
        verify_kpi_runtime_activation(
            metric="putaway",
            semantic_verification=semantic("putaway"),
            schema_verification=schema(),
            start_date=date(2026, 7, 30),
            end_date=date(2026, 8, 2),
        )


def test_non_unit_sensitive_metric_needs_no_runtime_bundle():
    assert (
        verify_kpi_runtime_activation(
            metric="orders",
            semantic_verification=semantic("orders"),
            schema_verification=schema(),
        )
        is None
    )
