from dataclasses import replace

import pytest

from app.kpi_provenance import activation_provenance_fingerprint, provenance_from_activation
from app.kpi_registry import KPI_REGISTRY
from app.kpi_release_guard import verify_kpi_registry_runtime_alignment


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64
FP_D = "d" * 64
FP_E = "e" * 64


def _as_executable(metric: str, query_id: str, schema_contract_id: str):
    """Build an executable-shaped fixture under the hardened registry definition.

    The release guard only verifies contract presence; registry binding cryptographic
    validation is exercised separately. Legacy bootstrap keeps this fixture focused on
    the missing-runtime/result-contract invariant instead of promotion mechanics.
    """

    return replace(
        KPI_REGISTRY[metric],
        review_state="reviewed",
        query_id=query_id,
        schema_contract_id=schema_contract_id,
        schema_contract_fingerprint=FP_A,
        semantic_contract_fingerprint=FP_B,
        query_template_fingerprint=FP_C,
        registry_binding_fingerprint=FP_D,
        legacy_bootstrap=True,
    )


def test_activation_provenance_is_deterministic_and_sensitive_to_lineage():
    base = activation_provenance_fingerprint(
        metric="picking",
        semantic_fingerprint=FP_A,
        schema_fingerprint=FP_B,
        schema_evidence_fingerprint=FP_C,
        unit_contract_fingerprint=FP_D,
        aggregation_contract_fingerprint=FP_E,
    )
    same = activation_provenance_fingerprint(
        metric="picking",
        semantic_fingerprint=FP_A,
        schema_fingerprint=FP_B,
        schema_evidence_fingerprint=FP_C,
        unit_contract_fingerprint=FP_D,
        aggregation_contract_fingerprint=FP_E,
    )
    changed = activation_provenance_fingerprint(
        metric="picking",
        semantic_fingerprint=FP_A,
        schema_fingerprint=FP_B,
        schema_evidence_fingerprint=FP_C,
        unit_contract_fingerprint=FP_E,
        aggregation_contract_fingerprint=FP_D,
    )
    assert len(base) == 64
    assert base == same
    assert base != changed


def test_policy_and_formula_contracts_change_combined_provenance():
    base = activation_provenance_fingerprint(
        metric="putaway",
        semantic_fingerprint=FP_A,
        schema_fingerprint=FP_B,
        schema_evidence_fingerprint=FP_C,
        policy_contract_fingerprint=FP_D,
        formula_contract_fingerprint=FP_E,
    )
    changed = activation_provenance_fingerprint(
        metric="putaway",
        semantic_fingerprint=FP_A,
        schema_fingerprint=FP_B,
        schema_evidence_fingerprint=FP_C,
        policy_contract_fingerprint=FP_E,
        formula_contract_fingerprint=FP_D,
    )
    assert base != changed


def test_provenance_from_activation_preserves_optional_runtime_nulls():
    digest = provenance_from_activation(
        metric="orders",
        semantic_verification={"fingerprint": FP_A},
        schema_verification={"observed_fingerprint": FP_B, "evidence_fingerprint": None},
        runtime_activation=None,
    )
    assert len(digest) == 64


def test_provenance_rejects_malformed_fingerprint():
    with pytest.raises(ValueError, match="kpi_provenance_invalid_fingerprint:schema"):
        activation_provenance_fingerprint(
            metric="orders",
            semantic_fingerprint=FP_A,
            schema_fingerprint="not-a-sha",
        )


def test_current_registry_runtime_alignment_passes():
    result = verify_kpi_registry_runtime_alignment()
    assert "orders" in result.executable_metrics
    assert {"nsfr", "pfr", "refund"}.issubset(set(result.result_contract_metrics))
    assert result.passed is True


def test_release_guard_blocks_picking_registry_activation_without_runtime_contract():
    registry = dict(KPI_REGISTRY)
    registry["picking"] = _as_executable(
        "picking", "ops.kpi.picking.v1", "ops.picking.v1"
    )
    with pytest.raises(ValueError, match="kpi_release_runtime_contract_missing:duration=picking"):
        verify_kpi_registry_runtime_alignment(registry=registry)


def test_release_guard_blocks_otp_registry_activation_without_rate_contract():
    registry = dict(KPI_REGISTRY)
    registry["otp"] = _as_executable("otp", "ops.kpi.otp.v1", "ops.otp.v1")
    with pytest.raises(ValueError, match="kpi_release_runtime_contract_missing:rate=otp"):
        verify_kpi_registry_runtime_alignment(registry=registry)


def test_release_guard_blocks_putaway_registry_activation_without_policy_contract():
    registry = dict(KPI_REGISTRY)
    registry["putaway"] = _as_executable(
        "putaway", "ops.kpi.putaway.v1", "ops.putaway.v1"
    )
    with pytest.raises(ValueError, match="kpi_release_runtime_contract_missing:putaway=putaway"):
        verify_kpi_registry_runtime_alignment(registry=registry)


def test_release_guard_blocks_nsfr_activation_without_result_contract():
    registry = dict(KPI_REGISTRY)
    registry["nsfr"] = _as_executable("nsfr", "ops.kpi.nsfr.v1", "ops.nsfr.v1")
    result_contracts = {"pfr": object(), "refund": object()}
    with pytest.raises(ValueError, match="kpi_release_runtime_contract_missing:result=nsfr"):
        verify_kpi_registry_runtime_alignment(
            registry=registry,
            result_contracts=result_contracts,
        )
