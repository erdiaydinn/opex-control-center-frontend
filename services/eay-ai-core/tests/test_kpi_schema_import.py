import pytest

from app.kpi_schema_evidence import verify_nsfr_schema_evidence
from app.kpi_schema_import import import_information_schema_rows


TABLE = "report_dmart_ops_nsfr_global_overview"


def _rows():
    return [
        {"table_name": TABLE, "column_name": "orders_ok", "data_type": "INT64"},
        {"table_name": TABLE, "column_name": "partial_cnt", "data_type": "INT64"},
        {"table_name": TABLE, "column_name": "refund_cnt", "data_type": "INT64"},
        {"table_name": TABLE, "column_name": "store_name", "data_type": "STRING"},
    ]


def test_information_schema_import_round_trips_into_reviewed_schema_evidence():
    evidence = import_information_schema_rows(
        _rows(),
        expected_table=TABLE,
        captured_at="2026-08-11T06:00:00Z",
        source="BigQuery INFORMATION_SCHEMA.COLUMNS export job BQ-123",
        reviewer="data-owner",
        reviewed=True,
    )
    verified = verify_nsfr_schema_evidence(evidence)
    assert verified["verified"] is True
    assert verified["column_types"]["orders_ok"] == "INT64"
    assert len(verified["fingerprint"]) == 64


def test_information_schema_import_rejects_mixed_tables():
    rows = _rows() + [
        {"table_name": "other_table", "column_name": "x", "data_type": "INT64"}
    ]
    with pytest.raises(ValueError, match="kpi_schema_import_unexpected_table"):
        import_information_schema_rows(
            rows,
            expected_table=TABLE,
            captured_at="2026-08-11T06:00:00Z",
            source="export",
            reviewer="data-owner",
            reviewed=True,
        )


def test_information_schema_import_rejects_conflicting_duplicate_column_types():
    rows = _rows() + [
        {"table_name": TABLE, "column_name": "refund_cnt", "data_type": "NUMERIC"}
    ]
    with pytest.raises(ValueError, match="kpi_schema_import_conflicting_duplicate"):
        import_information_schema_rows(
            rows,
            expected_table=TABLE,
            captured_at="2026-08-11T06:00:00Z",
            source="export",
            reviewer="data-owner",
            reviewed=True,
        )


def test_information_schema_import_rejects_missing_contract_fields():
    with pytest.raises(ValueError, match="kpi_schema_import_missing_fields"):
        import_information_schema_rows(
            [{"table_name": TABLE, "column_name": "x"}],
            expected_table=TABLE,
            captured_at="2026-08-11T06:00:00Z",
            source="export",
            reviewer="data-owner",
            reviewed=True,
        )


def test_information_schema_import_rejects_empty_export():
    with pytest.raises(ValueError, match="kpi_schema_import_empty_export"):
        import_information_schema_rows(
            [],
            expected_table=TABLE,
            captured_at="2026-08-11T06:00:00Z",
            source="export",
            reviewer="data-owner",
            reviewed=True,
        )
