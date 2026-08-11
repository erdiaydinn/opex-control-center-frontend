from dataclasses import replace

import pytest

from app.kpi_registry import KPI_REGISTRY, KpiDefinition, require_executable_kpi
from app.kpi_registry_integrity import verify_registry_binding


FP = "a" * 64


def test_orders_legacy_bootstrap_is_pinned_to_full_registry_binding():
    definition = KPI_REGISTRY["orders"]
    binding = verify_registry_binding(definition)
    assert binding.metric == "orders"
    assert binding.legacy_bootstrap is True
    assert binding.promotion_decision_fingerprint is None
    assert binding.query_template_fingerprint == definition.query_template_fingerprint
    assert binding.schema_contract_fingerprint == definition.schema_contract_fingerprint
    assert binding.semantic_contract_fingerprint == definition.semantic_contract_fingerprint
    assert binding.fingerprint == definition.registry_binding_fingerprint
    assert require_executable_kpi("orders").query_id == "ops.kpi.orders.v1"


def test_query_template_fingerprint_drift_blocks_execution():
    drifted = replace(KPI_REGISTRY["orders"], query_template_fingerprint="f" * 64)
    with pytest.raises(ValueError, match="kpi_registry_integrity_query_template_drift:orders"):
        verify_registry_binding(drifted)


def test_schema_contract_fingerprint_drift_blocks_execution():
    drifted = replace(KPI_REGISTRY["orders"], schema_contract_fingerprint="f" * 64)
    with pytest.raises(ValueError, match="kpi_registry_integrity_schema_contract_drift:orders"):
        verify_registry_binding(drifted)


def test_semantic_contract_fingerprint_drift_blocks_execution():
    drifted = replace(KPI_REGISTRY["orders"], semantic_contract_fingerprint="f" * 64)
    with pytest.raises(ValueError, match="kpi_registry_integrity_semantic_contract_drift:orders"):
        verify_registry_binding(drifted)


def test_composite_registry_binding_drift_blocks_execution():
    drifted = replace(KPI_REGISTRY["orders"], registry_binding_fingerprint="f" * 64)
    with pytest.raises(ValueError, match="kpi_registry_integrity_binding_drift:orders"):
        verify_registry_binding(drifted)


def test_new_executable_metric_requires_all_binding_fingerprints_and_promotion():
    definition = KpiDefinition(
        metric="otp",
        query_id="ops.kpi.otp.v1",
        review_state="reviewed",
        source_table="report__tableau_store_performance_report",
        value_semantics="OTP 4.25",
        schema_contract_id="ops.otp.v1",
        semantic_contract_id="ops.otp.semantic.v1",
        query_template_fingerprint=FP,
        registry_promotion_fingerprint="b" * 64,
    )
    assert definition.executable is False


def test_legacy_bootstrap_cannot_be_reused_for_new_metric():
    definition = KpiDefinition(
        metric="otp",
        query_id="ops.kpi.orders.v1",
        review_state="reviewed",
        source_table="report__tableau_store_performance_report",
        value_semantics="OTP 4.25",
        schema_contract_id="ops.otp.v1",
        semantic_contract_id="ops.otp.semantic.v1",
        schema_contract_fingerprint=FP,
        semantic_contract_fingerprint=FP,
        query_template_fingerprint=KPI_REGISTRY["orders"].query_template_fingerprint,
        registry_binding_fingerprint=FP,
        legacy_bootstrap=True,
    )
    with pytest.raises(ValueError, match="kpi_registry_integrity_legacy_bootstrap_forbidden"):
        verify_registry_binding(definition)
