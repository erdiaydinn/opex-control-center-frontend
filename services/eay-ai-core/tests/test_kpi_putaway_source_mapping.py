import pytest

from app.kpi_putaway_source_mapping import (
    PutawaySourceRoleMapping,
    verify_putaway_source_mapping,
)
from app.kpi_schema_evidence import KpiSchemaEvidence


def evidence(**overrides):
    payload = {
        "table_id": "dmart_ops_st_po_receiving_putaway_sku_details",
        "observed_columns": {
            "event_date": "DATE",
            "city_name": "STRING",
            "inbound_type": "STRING",
            "elapsed_min": "NUMERIC",
            "qty_initial": "INT64",
            "qty_shelf": "INT64",
            "warehouse": "STRING",
        },
        "captured_at": "2026-08-11T07:45:00Z",
        "source": "BigQuery INFORMATION_SCHEMA.COLUMNS export",
        "reviewer": "schema-reviewer",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiSchemaEvidence(**payload)


def mapping(e, **overrides):
    payload = {
        "table_id": "dmart_ops_st_po_receiving_putaway_sku_details",
        "role_to_column": {
            "date": "event_date",
            "city": "city_name",
            "inbound_kind": "inbound_type",
            "elapsed_minutes": "elapsed_min",
            "initial_qty": "qty_initial",
            "on_shelf_qty": "qty_shelf",
        },
        "schema_evidence_fingerprint": e.fingerprint,
        "reviewed_at": "2026-08-11T07:50:00Z",
        "reviewer": "metric-owner",
        "reviewed": True,
    }
    payload.update(overrides)
    return PutawaySourceRoleMapping(**payload)


def test_putaway_source_mapping_binds_roles_to_exact_schema_evidence():
    e = evidence()
    result = verify_putaway_source_mapping(e, mapping(e))
    assert result["verified"] is True
    assert result["role_to_column"]["elapsed_minutes"] == "elapsed_min"
    assert result["role_types"]["initial_qty"] == "INT64"
    assert result["schema_evidence_fingerprint"] == e.fingerprint
    assert len(result["mapping_fingerprint"]) == 64


def test_putaway_source_mapping_rejects_stale_schema_lineage():
    e = evidence()
    with pytest.raises(ValueError, match="putaway_source_mapping_schema_evidence_mismatch"):
        verify_putaway_source_mapping(
            e,
            mapping(e, schema_evidence_fingerprint="a" * 64),
        )


def test_putaway_source_mapping_requires_human_review():
    e = evidence()
    with pytest.raises(ValueError, match="putaway_source_mapping_human_review_required"):
        verify_putaway_source_mapping(e, mapping(e, reviewed=False, reviewer=None))


def test_putaway_source_mapping_rejects_unobserved_business_role_column():
    e = evidence()
    roles = dict(mapping(e).role_to_column)
    roles["elapsed_minutes"] = "putaway_duration"
    with pytest.raises(ValueError, match="putaway_source_mapping_unobserved_columns:putaway_duration"):
        verify_putaway_source_mapping(e, mapping(e, role_to_column=roles))


def test_putaway_source_mapping_rejects_wrong_elapsed_type():
    e = evidence(
        observed_columns={
            "event_date": "DATE",
            "city_name": "STRING",
            "inbound_type": "STRING",
            "elapsed_min": "STRING",
            "qty_initial": "INT64",
            "qty_shelf": "INT64",
        }
    )
    with pytest.raises(ValueError, match="putaway_source_mapping_invalid_type:elapsed_minutes:STRING"):
        verify_putaway_source_mapping(e, mapping(e))


def test_putaway_source_mapping_rejects_duplicate_role_columns():
    e = evidence()
    roles = dict(mapping(e).role_to_column)
    roles["on_shelf_qty"] = "qty_initial"
    with pytest.raises(ValueError, match="putaway_source_mapping_duplicate_columns:qty_initial"):
        verify_putaway_source_mapping(e, mapping(e, role_to_column=roles))
