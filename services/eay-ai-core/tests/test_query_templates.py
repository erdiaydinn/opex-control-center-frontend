from app.query_templates import TEMPLATES, compile_tool_plan
from app.tool_contracts import build_tool_plan
from app.tool_router import validate_read_only_sql


def test_ops_template_is_vetted_and_parameterized():
    plan = build_tool_plan("ops_kpi_query", {
        "metric": "orders", "start_date": "2026-08-01", "end_date": "2026-08-10",
        "stores": ["Fulya"], "limit": 50,
    })
    sql, params = compile_tool_plan(plan)
    validate_read_only_sql(sql)
    assert "@start_date" in sql and "@end_date" in sql
    assert params["stores"] == ["Fulya"]
    assert params["stores_empty"] is False


def test_model_authored_sql_is_disabled_by_contract():
    plan = build_tool_plan("catalog_query", {"query": "yumurta", "field": "product", "limit": 10})
    assert plan.model_authored_sql_allowed is False
    sql, params = compile_tool_plan(plan)
    assert params["query"] == "yumurta"
    assert TEMPLATES[plan.query_id].query_id == plan.query_id
