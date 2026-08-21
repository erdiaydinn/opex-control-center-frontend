import pytest

from app.kpi_registry import KPI_REGISTRY, get_kpi_definition, require_executable_kpi
from app.tool_contracts import build_tool_plan


def test_orders_is_the_only_reviewed_executable_kpi_contract():
    executable = sorted(name for name, item in KPI_REGISTRY.items() if item.executable)
    assert executable == ["orders"]
    orders = require_executable_kpi("orders")
    assert orders.query_id == "ops.kpi.orders.v1"
    assert orders.source_table == "curated_data_shared_coredata_business.orders"


def test_unverified_metric_fails_before_query_compilation():
    with pytest.raises(ValueError, match="metric_template_not_implemented:nsfr"):
        build_tool_plan(
            "ops_kpi_query",
            {
                "metric": "nsfr",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "stores": [],
                "limit": 20,
            },
        )


def test_blocked_metrics_keep_reason_and_semantics_for_review():
    for metric in ["cancel_rate", "nsfr", "pfr", "refund", "prep", "picking", "putaway", "otp", "defect"]:
        item = get_kpi_definition(metric)
        assert item.review_state == "blocked_schema_verification"
        assert item.query_id is None
        assert item.blocked_reason
        assert item.value_semantics


def test_unknown_metric_is_not_silently_coerced():
    with pytest.raises(ValueError, match="unknown_kpi_metric:made_up"):
        get_kpi_definition("made_up")
