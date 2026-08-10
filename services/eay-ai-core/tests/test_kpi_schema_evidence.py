import pytest

from app.kpi_schema_evidence import KpiSchemaEvidence, verify_nsfr_schema_evidence


def _evidence(**overrides):
    payload = {
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "observed_columns": {
            "successful_orders": "INT64",
            "pfr_orders": "INT64",
            "refund_orders": "INT64",
            "compensation_orders": "INT64",
            "nsfr_orders": "INT64",
            "unrelated_column": "STRING",
        },
        "captured_at": "2026-08-10T20:30:00Z",
        "source": "BigQuery INFORMATION_SCHEMA.COLUMNS export",
        "reviewer": "human-reviewer",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiSchemaEvidence(**payload)


def test_nsfr_schema_evidence_is_fingerprinted_and_projects_only_required_columns():
    result = verify_nsfr_schema_evidence(_evidence())
    assert result["verified"] is True
    assert result["column_types"] == {
        "successful_orders": "INT64",
        "pfr_orders": "INT64",
        "refund_orders": "INT64",
        "compensation_orders": "INT64",
        "nsfr_orders": "INT64",
    }
    assert len(result["fingerprint"]) == 64


def test_nsfr_schema_evidence_requires_human_review():
    with pytest.raises(ValueError, match="kpi_schema_evidence_human_review_required"):
        verify_nsfr_schema_evidence(_evidence(reviewed=False, reviewer=None))


def test_nsfr_schema_evidence_rejects_wrong_table():
    with pytest.raises(ValueError, match="kpi_schema_evidence_table_mismatch"):
        verify_nsfr_schema_evidence(_evidence(table_id="other_table"))


def test_nsfr_schema_evidence_rejects_missing_required_column():
    columns = dict(_evidence().observed_columns)
    columns.pop("refund_orders")
    with pytest.raises(ValueError, match="kpi_schema_evidence_missing_columns:refund_orders"):
        verify_nsfr_schema_evidence(_evidence(observed_columns=columns))


def test_nsfr_schema_evidence_rejects_untyped_required_column():
    columns = dict(_evidence().observed_columns)
    columns["refund_orders"] = ""
    with pytest.raises(ValueError, match="kpi_schema_evidence_type_required:refund_orders"):
        verify_nsfr_schema_evidence(_evidence(observed_columns=columns))


def test_nsfr_schema_evidence_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="kpi_schema_evidence_timezone_required"):
        verify_nsfr_schema_evidence(_evidence(captured_at="2026-08-10T20:30:00"))


def test_schema_evidence_fingerprint_changes_on_type_drift():
    baseline = _evidence()
    columns = dict(baseline.observed_columns)
    columns["refund_orders"] = "NUMERIC"
    drifted = _evidence(observed_columns=columns)
    assert baseline.fingerprint != drifted.fingerprint
