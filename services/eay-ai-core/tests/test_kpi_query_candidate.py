import pytest

from app.kpi_query_candidate import build_nsfr_query_candidate


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64
FP_D = "d" * 64


def approval(**overrides):
    payload = {
        "verified": True,
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "evidence_fingerprint": FP_A,
        "manifest_fingerprint": FP_B,
        "approval_fingerprint": FP_C,
    }
    payload.update(overrides)
    return payload


def mapping(**overrides):
    payload = {
        "verified": True,
        "metric_family": "nsfr_family",
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "schema_evidence_fingerprint": FP_A,
        "mapping_fingerprint": FP_D,
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


def test_nsfr_query_candidate_is_deterministic_and_never_executable():
    candidate = build_nsfr_query_candidate(
        candidate_id="nsfr-candidate-001",
        manifest_approval=approval(),
        semantic_mapping=mapping(),
    )
    assert candidate.executable is False
    assert "SUM(CAST(`partial_cnt` AS NUMERIC)) AS pfr_orders" in candidate.sql
    assert "AS successful_orders" in candidate.sql
    assert len(candidate.fingerprint) == 64


def test_nsfr_query_candidate_requires_same_schema_evidence_lineage():
    with pytest.raises(ValueError, match="kpi_query_candidate_schema_evidence_mismatch"):
        build_nsfr_query_candidate(
            candidate_id="nsfr-candidate-001",
            manifest_approval=approval(),
            semantic_mapping=mapping(schema_evidence_fingerprint="e" * 64),
        )


def test_nsfr_query_candidate_rejects_identifier_injection():
    roles = dict(mapping()["role_to_column"])
    roles["refund_orders"] = "refund_cnt`; DROP TABLE x; --"
    with pytest.raises(ValueError, match="kpi_query_candidate_invalid_column:refund_orders"):
        build_nsfr_query_candidate(
            candidate_id="nsfr-candidate-001",
            manifest_approval=approval(),
            semantic_mapping=mapping(role_to_column=roles),
        )


def test_nsfr_query_candidate_rejects_non_numeric_business_role():
    types = dict(mapping()["role_types"])
    types["refund_orders"] = "STRING"
    with pytest.raises(ValueError, match="kpi_query_candidate_non_numeric_role:refund_orders:STRING"):
        build_nsfr_query_candidate(
            candidate_id="nsfr-candidate-001",
            manifest_approval=approval(),
            semantic_mapping=mapping(role_types=types),
        )


def test_nsfr_query_candidate_requires_approved_manifest():
    with pytest.raises(ValueError, match="kpi_query_candidate_schema_approval_required"):
        build_nsfr_query_candidate(
            candidate_id="nsfr-candidate-001",
            manifest_approval=approval(verified=False),
            semantic_mapping=mapping(),
        )
