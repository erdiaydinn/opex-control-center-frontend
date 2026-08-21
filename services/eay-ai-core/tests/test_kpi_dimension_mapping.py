import pytest

from app.kpi_dimension_mapping import KpiDimensionRoleMapping, verify_nsfr_dimension_mapping
from app.kpi_schema_evidence import KpiSchemaEvidence


def evidence(**overrides):
    payload = {
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "observed_columns": {
            "event_date": "DATE",
            "store_label": "STRING",
            "orders_ok": "INT64",
        },
        "captured_at": "2026-08-11T06:50:00Z",
        "source": "BigQuery INFORMATION_SCHEMA.COLUMNS export",
        "reviewer": "schema-reviewer",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiSchemaEvidence(**payload)


def mapping(ev, **overrides):
    payload = {
        "metric_family": "nsfr_family",
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "role_to_column": {"date": "event_date", "store": "store_label"},
        "schema_evidence_fingerprint": ev.fingerprint,
        "reviewed_at": "2026-08-11T06:55:00Z",
        "reviewer": "metric-owner",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiDimensionRoleMapping(**payload)


def test_nsfr_dimension_mapping_binds_date_and_store_to_reviewed_schema():
    ev = evidence()
    result = verify_nsfr_dimension_mapping(ev, mapping(ev))
    assert result["verified"] is True
    assert result["role_to_column"] == {"date": "event_date", "store": "store_label"}
    assert result["role_types"] == {"date": "DATE", "store": "STRING"}
    assert result["schema_evidence_fingerprint"] == ev.fingerprint
    assert len(result["mapping_fingerprint"]) == 64


def test_nsfr_dimension_mapping_rejects_stale_schema_fingerprint():
    ev = evidence()
    with pytest.raises(ValueError, match="kpi_dimension_mapping_schema_evidence_mismatch"):
        verify_nsfr_dimension_mapping(
            ev,
            mapping(ev, schema_evidence_fingerprint="a" * 64),
        )


def test_nsfr_dimension_mapping_rejects_unobserved_dimension():
    ev = evidence()
    with pytest.raises(ValueError, match="kpi_dimension_mapping_unobserved_column:store:vendor_name"):
        verify_nsfr_dimension_mapping(
            ev,
            mapping(ev, role_to_column={"date": "event_date", "store": "vendor_name"}),
        )


def test_nsfr_dimension_mapping_rejects_wrong_date_type():
    ev = evidence(observed_columns={"event_date": "STRING", "store_label": "STRING"})
    with pytest.raises(ValueError, match="kpi_dimension_mapping_invalid_date_type:STRING"):
        verify_nsfr_dimension_mapping(ev, mapping(ev))


def test_nsfr_dimension_mapping_requires_human_review():
    ev = evidence()
    with pytest.raises(ValueError, match="kpi_dimension_mapping_human_review_required"):
        verify_nsfr_dimension_mapping(ev, mapping(ev, reviewed=False, reviewer=None))
