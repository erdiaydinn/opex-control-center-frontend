import pytest

from app.kpi_schema_evidence import KpiSchemaEvidence
from app.kpi_source_semantics import (
    DurationSourceSemantics,
    RateSourceSemantics,
    verify_duration_source_semantics,
    verify_otp_source_semantics,
)


def evidence(table_id, columns):
    return KpiSchemaEvidence(
        table_id=table_id,
        observed_columns=columns,
        captured_at="2026-08-11T07:00:00Z",
        source="BigQuery INFORMATION_SCHEMA.COLUMNS export",
        reviewer="schema-reviewer",
        reviewed=True,
    )


def test_picking_picker_day_requires_explicit_order_weight_and_unit():
    ev = evidence(
        "dmart_ops_picker_individual_performance_daily",
        {
            "work_date": "DATE",
            "store_label": "STRING",
            "avg_pick_min": "FLOAT64",
            "eligible_order_cnt": "INT64",
        },
    )
    semantics = DurationSourceSemantics(
        metric="picking",
        table_id=ev.table_id,
        role_to_column={
            "date": "work_date",
            "store": "store_label",
            "duration_value": "avg_pick_min",
            "eligible_orders": "eligible_order_cnt",
        },
        schema_evidence_fingerprint=ev.fingerprint,
        source_grain="picker_day",
        source_unit="minutes",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    result = verify_duration_source_semantics(ev, semantics)
    assert result["source_unit"] == "minutes"
    assert result["weight_column"] == "eligible_order_cnt"
    assert result["unit_contract"].source_unit == "minutes"
    assert result["aggregation_contract"].source_grain == "picker_day"
    assert result["aggregation_contract"].weight_field == "eligible_order_cnt"
    assert len(result["source_semantics_fingerprint"]) == 64


def test_picking_picker_day_rejects_missing_weight_role():
    ev = evidence(
        "dmart_ops_picker_individual_performance_daily",
        {"work_date": "DATE", "store_label": "STRING", "avg_pick_sec": "FLOAT64"},
    )
    semantics = DurationSourceSemantics(
        metric="picking",
        table_id=ev.table_id,
        role_to_column={"date": "work_date", "store": "store_label", "duration_value": "avg_pick_sec"},
        schema_evidence_fingerprint=ev.fingerprint,
        source_grain="picker_day",
        source_unit="seconds",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    with pytest.raises(ValueError, match="kpi_source_semantics_missing_role:eligible_orders"):
        verify_duration_source_semantics(ev, semantics)


def test_prep_event_grain_does_not_invent_weight_column():
    ev = evidence(
        "report__tableau_store_performance_report",
        {"event_day": "DATE", "vendor_name": "STRING", "prep_secs": "NUMERIC"},
    )
    semantics = DurationSourceSemantics(
        metric="prep",
        table_id=ev.table_id,
        role_to_column={"date": "event_day", "store": "vendor_name", "duration_value": "prep_secs"},
        schema_evidence_fingerprint=ev.fingerprint,
        source_grain="event",
        source_unit="seconds",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    result = verify_duration_source_semantics(ev, semantics)
    assert result["weight_column"] is None
    assert result["aggregation_contract"].weight_field is None


def test_duration_source_semantics_rejects_stale_schema_evidence():
    ev = evidence(
        "report__tableau_store_performance_report",
        {"event_day": "DATE", "vendor_name": "STRING", "prep_secs": "NUMERIC"},
    )
    semantics = DurationSourceSemantics(
        metric="prep",
        table_id=ev.table_id,
        role_to_column={"date": "event_day", "store": "vendor_name", "duration_value": "prep_secs"},
        schema_evidence_fingerprint="a" * 64,
        source_grain="event",
        source_unit="seconds",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    with pytest.raises(ValueError, match="kpi_source_semantics_schema_evidence_mismatch"):
        verify_duration_source_semantics(ev, semantics)


def test_otp_requires_additive_numerator_denominator_lineage():
    ev = evidence(
        "report__tableau_store_performance_report",
        {
            "event_day": "DATE",
            "vendor_name": "STRING",
            "late_rate": "FLOAT64",
            "late_orders": "INT64",
            "eligible_orders": "INT64",
        },
    )
    semantics = RateSourceSemantics(
        metric="otp",
        table_id=ev.table_id,
        role_to_column={
            "date": "event_day",
            "store": "vendor_name",
            "late_prep_rate": "late_rate",
            "late_prep_orders": "late_orders",
            "eligible_orders": "eligible_orders",
        },
        schema_evidence_fingerprint=ev.fingerprint,
        source_scale="fraction",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    result = verify_otp_source_semantics(ev, semantics)
    assert result["source_scale"] == "fraction"
    assert result["rate_contract"].source_scale == "fraction"
    assert result["late_prep_rate_column"] == "late_rate"
    assert result["late_prep_orders_column"] == "late_orders"
    assert result["eligible_orders_column"] == "eligible_orders"
    assert result["aggregation_contract"].numerator_field == "late_orders"
    assert result["aggregation_contract"].denominator_field == "eligible_orders"
    assert result["aggregation_contract"].aggregation_kind == "complement_ratio_of_sums"


def test_otp_preaggregated_rate_is_optional_but_not_sufficient():
    ev = evidence(
        "report__tableau_store_performance_report",
        {
            "event_day": "DATE",
            "vendor_name": "STRING",
            "late_orders": "INT64",
            "eligible_orders": "INT64",
        },
    )
    semantics = RateSourceSemantics(
        metric="otp",
        table_id=ev.table_id,
        role_to_column={
            "date": "event_day",
            "store": "vendor_name",
            "late_prep_orders": "late_orders",
            "eligible_orders": "eligible_orders",
        },
        schema_evidence_fingerprint=ev.fingerprint,
        source_scale="percent",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    result = verify_otp_source_semantics(ev, semantics)
    assert result["late_prep_rate_column"] is None
    assert result["aggregation_contract"].numerator_field == "late_orders"


def test_otp_rejects_rate_only_mapping_without_additive_lineage():
    ev = evidence(
        "report__tableau_store_performance_report",
        {"event_day": "DATE", "vendor_name": "STRING", "late_rate": "FLOAT64"},
    )
    semantics = RateSourceSemantics(
        metric="otp",
        table_id=ev.table_id,
        role_to_column={"date": "event_day", "store": "vendor_name", "late_prep_rate": "late_rate"},
        schema_evidence_fingerprint=ev.fingerprint,
        source_scale="percent",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    with pytest.raises(ValueError, match="kpi_source_semantics_missing_role:late_prep_orders"):
        verify_otp_source_semantics(ev, semantics)


def test_otp_rejects_string_denominator_column():
    ev = evidence(
        "report__tableau_store_performance_report",
        {
            "event_day": "DATE",
            "vendor_name": "STRING",
            "late_orders": "INT64",
            "eligible_orders": "STRING",
        },
    )
    semantics = RateSourceSemantics(
        metric="otp",
        table_id=ev.table_id,
        role_to_column={
            "date": "event_day",
            "store": "vendor_name",
            "late_prep_orders": "late_orders",
            "eligible_orders": "eligible_orders",
        },
        schema_evidence_fingerprint=ev.fingerprint,
        source_scale="percent",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    with pytest.raises(ValueError, match="kpi_source_semantics_invalid_type:eligible_orders:STRING"):
        verify_otp_source_semantics(ev, semantics)


def test_otp_rejects_same_column_for_numerator_and_denominator():
    ev = evidence(
        "report__tableau_store_performance_report",
        {"event_day": "DATE", "vendor_name": "STRING", "orders": "INT64"},
    )
    semantics = RateSourceSemantics(
        metric="otp",
        table_id=ev.table_id,
        role_to_column={
            "date": "event_day",
            "store": "vendor_name",
            "late_prep_orders": "orders",
            "eligible_orders": "orders",
        },
        schema_evidence_fingerprint=ev.fingerprint,
        source_scale="percent",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer="metric-owner",
        reviewed=True,
    )
    with pytest.raises(ValueError, match="kpi_source_semantics_otp_numerator_denominator_must_differ"):
        verify_otp_source_semantics(ev, semantics)


def test_source_semantics_requires_human_review():
    ev = evidence(
        "report__tableau_store_performance_report",
        {"event_day": "DATE", "vendor_name": "STRING", "prep_secs": "NUMERIC"},
    )
    semantics = DurationSourceSemantics(
        metric="prep",
        table_id=ev.table_id,
        role_to_column={"date": "event_day", "store": "vendor_name", "duration_value": "prep_secs"},
        schema_evidence_fingerprint=ev.fingerprint,
        source_grain="event",
        source_unit="seconds",
        reviewed_at="2026-08-11T07:05:00Z",
        reviewer=None,
        reviewed=False,
    )
    with pytest.raises(ValueError, match="kpi_source_semantics_human_review_required"):
        verify_duration_source_semantics(ev, semantics)
