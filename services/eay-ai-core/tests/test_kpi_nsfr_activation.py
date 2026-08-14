import pytest

from app.kpi_activation_gate import verify_nsfr_family_activation
from app.kpi_result_validation import KPI_RESULT_CONTRACTS


FP_SEMANTIC = "a" * 64
FP_SCHEMA = "b" * 64
FP_EVIDENCE = "c" * 64
FP_MAPPING = "d" * 64


def _semantic(metric="nsfr"):
    return {"metric": metric, "reviewed": True, "fingerprint": FP_SEMANTIC}


def _schema(**overrides):
    payload = {
        "verified": True,
        "observed_fingerprint": FP_SCHEMA,
        "evidence_fingerprint": FP_EVIDENCE,
    }
    payload.update(overrides)
    return payload


def _mapping(**overrides):
    payload = {
        "verified": True,
        "metric_family": "nsfr_family",
        "schema_evidence_fingerprint": FP_EVIDENCE,
        "mapping_fingerprint": FP_MAPPING,
    }
    payload.update(overrides)
    return payload


def test_nsfr_activation_binds_schema_semantics_mapping_and_result_contract():
    result = verify_nsfr_family_activation(
        metric="nsfr",
        semantic_verification=_semantic(),
        schema_verification=_schema(),
        semantic_mapping_verification=_mapping(),
        result_contract=KPI_RESULT_CONTRACTS["nsfr"],
    )
    assert result.metric == "nsfr"
    assert result.schema_evidence_fingerprint == FP_EVIDENCE
    assert result.semantic_mapping_fingerprint == FP_MAPPING
    assert len(result.result_contract_fingerprint) == 64


def test_nsfr_activation_rejects_missing_schema_evidence():
    with pytest.raises(ValueError, match="kpi_activation_schema_evidence_required"):
        verify_nsfr_family_activation(
            metric="nsfr",
            semantic_verification=_semantic(),
            schema_verification=_schema(evidence_fingerprint=None),
            semantic_mapping_verification=_mapping(),
            result_contract=KPI_RESULT_CONTRACTS["nsfr"],
        )


def test_nsfr_activation_rejects_mapping_from_different_schema_observation():
    with pytest.raises(ValueError, match="kpi_activation_semantic_mapping_schema_mismatch"):
        verify_nsfr_family_activation(
            metric="nsfr",
            semantic_verification=_semantic(),
            schema_verification=_schema(),
            semantic_mapping_verification=_mapping(schema_evidence_fingerprint="e" * 64),
            result_contract=KPI_RESULT_CONTRACTS["nsfr"],
        )


def test_nsfr_activation_rejects_unreviewed_semantic_mapping():
    with pytest.raises(ValueError, match="kpi_activation_semantic_mapping_required"):
        verify_nsfr_family_activation(
            metric="nsfr",
            semantic_verification=_semantic(),
            schema_verification=_schema(),
            semantic_mapping_verification=_mapping(verified=False),
            result_contract=KPI_RESULT_CONTRACTS["nsfr"],
        )


def test_nsfr_activation_rejects_result_contract_for_different_metric():
    with pytest.raises(ValueError, match="kpi_activation_result_contract_metric_mismatch"):
        verify_nsfr_family_activation(
            metric="pfr",
            semantic_verification=_semantic(metric="pfr"),
            schema_verification=_schema(),
            semantic_mapping_verification=_mapping(),
            result_contract=KPI_RESULT_CONTRACTS["nsfr"],
        )


def test_nsfr_activation_is_not_reused_for_other_kpis():
    with pytest.raises(ValueError, match="kpi_activation_not_nsfr_family_metric"):
        verify_nsfr_family_activation(
            metric="otp",
            semantic_verification=_semantic(metric="otp"),
            schema_verification=_schema(),
            semantic_mapping_verification=_mapping(),
            result_contract=KPI_RESULT_CONTRACTS["nsfr"],
        )
