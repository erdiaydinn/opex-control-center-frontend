import pytest

from app.kpi_schema_evidence import KpiSchemaEvidence
from app.kpi_semantic_mapping import (
    KpiSemanticRoleMapping,
    verify_nsfr_family_role_mapping,
)


def _evidence(**overrides):
    payload = {
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "observed_columns": {
            "orders_ok": "INT64",
            "partial_cnt": "INT64",
            "refund_cnt": "INT64",
            "comp_cnt": "INT64",
            "nsfr_cnt": "INT64",
            "store_name": "STRING",
        },
        "captured_at": "2026-08-11T05:30:00Z",
        "source": "BigQuery INFORMATION_SCHEMA.COLUMNS export",
        "reviewer": "schema-reviewer",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiSchemaEvidence(**payload)


def _mapping(evidence, **overrides):
    payload = {
        "metric_family": "nsfr_family",
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "role_to_column": {
            "eligible_orders": "orders_ok",
            "pfr_orders": "partial_cnt",
            "refund_orders": "refund_cnt",
            "compensation_orders": "comp_cnt",
            "nsfr_orders": "nsfr_cnt",
        },
        "schema_evidence_fingerprint": evidence.fingerprint,
        "reviewed_at": "2026-08-11T05:40:00Z",
        "reviewer": "metric-owner",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiSemanticRoleMapping(**payload)


def test_nsfr_mapping_allows_real_column_names_different_from_business_roles():
    evidence = _evidence()
    result = verify_nsfr_family_role_mapping(evidence, _mapping(evidence))
    assert result["verified"] is True
    assert result["role_to_column"]["pfr_orders"] == "partial_cnt"
    assert result["role_types"]["pfr_orders"] == "INT64"
    assert result["schema_evidence_fingerprint"] == evidence.fingerprint
    assert len(result["mapping_fingerprint"]) == 64


def test_nsfr_mapping_rejects_stale_schema_evidence_fingerprint():
    evidence = _evidence()
    mapping = _mapping(evidence, schema_evidence_fingerprint="a" * 64)
    with pytest.raises(ValueError, match="kpi_semantic_mapping_schema_evidence_mismatch"):
        verify_nsfr_family_role_mapping(evidence, mapping)


def test_nsfr_mapping_requires_human_review():
    evidence = _evidence()
    with pytest.raises(ValueError, match="kpi_semantic_mapping_human_review_required"):
        verify_nsfr_family_role_mapping(
            evidence,
            _mapping(evidence, reviewed=False, reviewer=None),
        )


def test_nsfr_mapping_rejects_unobserved_column_instead_of_guessing():
    evidence = _evidence()
    roles = dict(_mapping(evidence).role_to_column)
    roles["refund_orders"] = "refund_orders"
    with pytest.raises(ValueError, match="kpi_semantic_mapping_unobserved_columns:refund_orders"):
        verify_nsfr_family_role_mapping(
            evidence,
            _mapping(evidence, role_to_column=roles),
        )


def test_nsfr_mapping_rejects_one_column_reused_for_two_business_roles():
    evidence = _evidence()
    roles = dict(_mapping(evidence).role_to_column)
    roles["refund_orders"] = "partial_cnt"
    with pytest.raises(ValueError, match="kpi_semantic_mapping_duplicate_columns:partial_cnt"):
        verify_nsfr_family_role_mapping(
            evidence,
            _mapping(evidence, role_to_column=roles),
        )


def test_nsfr_mapping_rejects_missing_business_role():
    evidence = _evidence()
    roles = dict(_mapping(evidence).role_to_column)
    roles.pop("compensation_orders")
    with pytest.raises(ValueError, match="kpi_semantic_mapping_missing_roles:compensation_orders"):
        verify_nsfr_family_role_mapping(
            evidence,
            _mapping(evidence, role_to_column=roles),
        )
