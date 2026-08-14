import pytest

from app.kpi_schema_evidence import KpiSchemaEvidence, verify_nsfr_schema_evidence


def _evidence(**overrides):
    payload = {
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "observed_columns": {
            "orders_ok": "INT64",
            "partial_cnt": "INT64",
            "refund_cnt": "INT64",
            "comp_cnt": "INT64",
            "nsfr_cnt": "INT64",
            "unrelated_column": "STRING",
        },
        "captured_at": "2026-08-11T05:30:00Z",
        "source": "BigQuery INFORMATION_SCHEMA.COLUMNS export",
        "reviewer": "human-reviewer",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiSchemaEvidence(**payload)


def test_nsfr_schema_evidence_fingerprints_full_observation_without_guessing_roles():
    result = verify_nsfr_schema_evidence(_evidence())
    assert result["verified"] is True
    assert result["required_columns"] == []
    assert result["column_types"]["orders_ok"] == "INT64"
    assert result["column_types"]["partial_cnt"] == "INT64"
    assert "successful_orders" not in result["column_types"]
    assert len(result["fingerprint"]) == 64


def test_nsfr_schema_evidence_requires_human_review():
    with pytest.raises(ValueError, match="kpi_schema_evidence_human_review_required"):
        verify_nsfr_schema_evidence(_evidence(reviewed=False, reviewer=None))


def test_nsfr_schema_evidence_rejects_wrong_table():
    with pytest.raises(ValueError, match="kpi_schema_evidence_table_mismatch"):
        verify_nsfr_schema_evidence(_evidence(table_id="other_table"))


def test_schema_observation_does_not_require_semantic_role_named_columns():
    # Role semantics are reviewed later by kpi_semantic_mapping. Schema evidence must
    # remain a factual INFORMATION_SCHEMA observation rather than infer business meaning.
    result = verify_nsfr_schema_evidence(
        _evidence(observed_columns={"a": "INT64", "b": "STRING"})
    )
    assert result["verified"] is True
    assert result["column_types"] == {"a": "INT64", "b": "STRING"}


def test_nsfr_schema_evidence_rejects_untyped_observed_column():
    columns = dict(_evidence().observed_columns)
    columns["refund_cnt"] = ""
    with pytest.raises(ValueError, match="kpi_schema_evidence_type_required:refund_cnt"):
        verify_nsfr_schema_evidence(_evidence(observed_columns=columns))


def test_nsfr_schema_evidence_rejects_empty_schema():
    with pytest.raises(ValueError, match="kpi_schema_evidence_empty_schema"):
        verify_nsfr_schema_evidence(_evidence(observed_columns={}))


def test_nsfr_schema_evidence_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="kpi_schema_evidence_timezone_required"):
        verify_nsfr_schema_evidence(_evidence(captured_at="2026-08-11T05:30:00"))


def test_schema_evidence_fingerprint_changes_on_type_drift():
    baseline = _evidence()
    columns = dict(baseline.observed_columns)
    columns["refund_cnt"] = "NUMERIC"
    drifted = _evidence(observed_columns=columns)
    assert baseline.fingerprint != drifted.fingerprint
