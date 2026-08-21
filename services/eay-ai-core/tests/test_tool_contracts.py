from datetime import date

import pytest

from app.tool_contracts import build_tool_plan


def test_ops_plan_never_allows_model_sql():
    plan = build_tool_plan(
        "ops_kpi_query",
        {
            "metric": "orders",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "stores": ["Fulya"],
            "limit": 20,
        },
    )
    assert plan.query_id == "ops.kpi.orders.v1"
    assert plan.model_authored_sql_allowed is False
    assert plan.required_scope == ["ops:read"]


def test_ops_plan_rejects_metric_without_reviewed_schema_contract():
    with pytest.raises(ValueError, match="metric_template_not_implemented:nsfr"):
        build_tool_plan(
            "ops_kpi_query",
            {
                "metric": "nsfr",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "stores": ["Fulya"],
                "limit": 20,
            },
        )


def test_ops_plan_rejects_unbounded_date_window():
    with pytest.raises(ValueError, match="date_window_too_large"):
        build_tool_plan(
            "ops_kpi_query",
            {"metric": "orders", "start_date": "2024-01-01", "end_date": "2026-08-10"},
        )


def test_regulatory_plan_has_legal_and_catalog_scope():
    plan = build_tool_plan(
        "regulatory_impact_query",
        {"instrument_id": "tgk-new-food", "as_of": "2026-08-10", "entities": ["sku", "supplier"]},
    )
    assert "legal:read" in plan.required_scope
    assert "catalog:read" in plan.required_scope
    assert plan.arguments["instrument_id"] == "tgk-new-food"
