from app.kpi_aggregation_contracts import WeightedAverageContract
from app.kpi_rate_aggregation import RateAggregationContract
from app.kpi_runtime_query_candidate import build_duration_query_candidate, build_otp_query_candidate
from app.kpi_unit_contracts import DurationContract, RateContract

FP = "a" * 64
SEM_FP = "b" * 64


def test_picker_day_query_uses_weighted_aggregation():
    source = {
        "metric": "picking",
        "table_id": "dmart_ops_picker_individual_performance_daily",
        "date_column": "report_date",
        "store_column": "store_name",
        "duration_column": "seconds_per_order",
        "weight_column": "eligible_orders",
        "source_grain": "picker_day",
        "source_unit": "seconds",
        "schema_evidence_fingerprint": FP,
        "source_semantics_fingerprint": SEM_FP,
        "unit_contract": DurationContract(metric="picking", source_unit="seconds"),
        "aggregation_contract": WeightedAverageContract(metric="picking", source_grain="picker_day", value_field="seconds_per_order", weight_field="eligible_orders", output_unit="seconds_per_order"),
        "reviewed": True,
    }
    candidate = build_duration_query_candidate(candidate_id="picking-v1", verified_source=source)
    assert candidate.executable is False
    assert "SAFE_DIVIDE(SUM(CAST(`seconds_per_order` AS NUMERIC) * CAST(`eligible_orders` AS NUMERIC)), SUM(CAST(`eligible_orders` AS NUMERIC)))" in candidate.sql
    assert "AVG(" not in candidate.sql


def test_otp_query_uses_complement_ratio_of_sums():
    source = {
        "metric": "otp",
        "table_id": "report__tableau_store_performance_report",
        "date_column": "report_date",
        "store_column": "store_name",
        "late_prep_orders_column": "late_prep_orders",
        "eligible_orders_column": "eligible_orders",
        "schema_evidence_fingerprint": FP,
        "source_semantics_fingerprint": SEM_FP,
        "rate_contract": RateContract(metric="otp", source_scale="percent"),
        "aggregation_contract": RateAggregationContract(metric="otp", numerator_field="late_prep_orders", denominator_field="eligible_orders", aggregation_kind="complement_ratio_of_sums"),
        "reviewed": True,
    }
    candidate = build_otp_query_candidate(candidate_id="otp-v1", verified_source=source)
    assert candidate.executable is False
    assert "100 - (SAFE_DIVIDE(SUM(CAST(`late_prep_orders` AS NUMERIC)), SUM(CAST(`eligible_orders` AS NUMERIC))) * 100)" in candidate.sql
    assert "AVG(" not in candidate.sql
