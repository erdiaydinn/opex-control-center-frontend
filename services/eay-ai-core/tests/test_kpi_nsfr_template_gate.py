import pytest

from app.kpi_activation_gate import KpiNsfrActivationBundle
from app.kpi_nsfr_template_gate import verify_nsfr_template_activation_review
from app.kpi_query_candidate import build_parameterized_nsfr_query_candidate
from app.kpi_result_validation import KPI_RESULT_CONTRACTS


FP_EVIDENCE = "a" * 64
FP_MANIFEST = "b" * 64
FP_APPROVAL = "c" * 64
FP_SEMANTIC = "d" * 64
FP_DIMENSION = "e" * 64
FP_SCHEMA = "f" * 64
FP_SEMANTIC_CONTRACT = "1" * 64


def manifest(**overrides):
    payload = {
        "verified": True,
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "evidence_fingerprint": FP_EVIDENCE,
        "manifest_fingerprint": FP_MANIFEST,
        "approval_fingerprint": FP_APPROVAL,
    }
    payload.update(overrides)
    return payload


def measures(**overrides):
    payload = {
        "verified": True,
        "metric_family": "nsfr_family",
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "schema_evidence_fingerprint": FP_EVIDENCE,
        "mapping_fingerprint": FP_SEMANTIC,
        "role_to_column": {
            "eligible_orders": "orders_ok",
            "pfr_orders": "partial_cnt",
            "refund_orders": "refund_cnt",
            "compensation_orders": "comp_cnt",
            "nsfr_orders": "nsfr_cnt",
        },
        "role_types": {
            "eligible_orders": "INT64",
            "pfr_orders": "INT64",
            "refund_orders": "INT64",
            "compensation_orders": "INT64",
            "nsfr_orders": "INT64",
        },
    }
    payload.update(overrides)
    return payload


def dimensions(**overrides):
    payload = {
        "verified": True,
        "metric_family": "nsfr_family",
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "schema_evidence_fingerprint": FP_EVIDENCE,
        "mapping_fingerprint": FP_DIMENSION,
        "role_to_column": {"date": "event_date", "store": "store_label"},
        "role_types": {"date": "DATE", "store": "STRING"},
    }
    payload.update(overrides)
    return payload


def activation(metric="nsfr"):
    contract = KPI_RESULT_CONTRACTS[metric]
    return KpiNsfrActivationBundle(
        metric=metric,
        semantic_fingerprint=FP_SEMANTIC_CONTRACT,
        schema_fingerprint=FP_SCHEMA,
        schema_evidence_fingerprint=FP_EVIDENCE,
        semantic_mapping_fingerprint=FP_SEMANTIC,
        result_contract_fingerprint=contract.fingerprint,
    )


def candidate():
    return build_parameterized_nsfr_query_candidate(
        candidate_id="nsfr-parameterized-review-001",
        manifest_approval=manifest(),
        semantic_mapping=measures(),
        dimension_mapping=dimensions(),
    )


def test_nsfr_template_gate_seals_complete_lineage_without_activating():
    review = verify_nsfr_template_activation_review(
        activation=activation(),
        manifest_approval=manifest(),
        dimension_mapping=dimensions(),
        query_candidate=candidate(),
        result_contract=KPI_RESULT_CONTRACTS["nsfr"],
    )
    assert review.executable is False
    assert review.schema_evidence_fingerprint == FP_EVIDENCE
    assert review.dimension_mapping_fingerprint == FP_DIMENSION
    assert review.query_candidate_fingerprint == candidate().fingerprint
    assert len(review.fingerprint) == 64


def test_nsfr_template_gate_rejects_candidate_from_different_dimension_mapping():
    altered = dimensions(mapping_fingerprint="9" * 64)
    with pytest.raises(ValueError, match="nsfr_template_gate_candidate_dimension_mapping_mismatch"):
        verify_nsfr_template_activation_review(
            activation=activation(),
            manifest_approval=manifest(),
            dimension_mapping=altered,
            query_candidate=candidate(),
            result_contract=KPI_RESULT_CONTRACTS["nsfr"],
        )


def test_nsfr_template_gate_rejects_stale_manifest_approval_lineage():
    with pytest.raises(ValueError, match="nsfr_template_gate_candidate_approval_mismatch"):
        verify_nsfr_template_activation_review(
            activation=activation(),
            manifest_approval=manifest(approval_fingerprint="9" * 64),
            dimension_mapping=dimensions(),
            query_candidate=candidate(),
            result_contract=KPI_RESULT_CONTRACTS["nsfr"],
        )


def test_nsfr_template_gate_rejects_wrong_result_contract():
    with pytest.raises(ValueError, match="nsfr_template_gate_result_metric_mismatch"):
        verify_nsfr_template_activation_review(
            activation=activation("nsfr"),
            manifest_approval=manifest(),
            dimension_mapping=dimensions(),
            query_candidate=candidate(),
            result_contract=KPI_RESULT_CONTRACTS["refund"],
        )
