from pathlib import Path

from app.budget_main import app


def test_master28_routes_are_mounted():
    paths = set(app.openapi()["paths"])
    for path in (
        "/v1/budget/planning/scenarios",
        "/v1/budget/planning/scenarios/{scenario_id}/assumptions",
        "/v1/budget/planning/scenarios/{scenario_id}/driver-lines",
        "/v1/budget/planning/scenarios/{scenario_id}/allocations",
        "/v1/budget/planning/scenarios/{scenario_id}/publish",
        "/v1/budget/planning/plans/{plan_id}/snapshot",
    ):
        assert path in paths


def test_master28_migration_is_fail_closed():
    text = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0037_budget_planning_authority.py"
    ).read_text()
    for token in (
        "fk_budget_forecast_exact_scope",
        "budget_plan_snapshot",
        "budget_capture_activation_snapshot",
        "budget_active_content_guard",
        "budget_scenario",
        "budget_scenario_assumption",
        "budget_scenario_line",
        "budget_allocation_rule",
        "budget_scenario_publish_guard",
        "FORCE ROW LEVEL SECURITY",
        "REVOKE UPDATE ON budget_line,fiscal_period,budget_plan",
    ):
        assert token in text


def test_master28_rolling_forecast_never_overwrites_accounting_truth():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/modules/budget/planning_engine.py"
    ).read_text().lower()
    assert "update actual" not in source
    assert "update commitment" not in source
    assert "update forecast" not in source
