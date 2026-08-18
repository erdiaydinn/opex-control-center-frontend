from pathlib import Path


def test_master28_global_snapshot_scope_and_published_scenario_immutability_are_db_enforced():
    text = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0040_budget_planning_hardening.py"
    ).read_text()
    assert "current_setting('app.budget_cost_center_ids',true)='__all__'" in text
    assert "published scenario root is immutable" in text
    assert "GRANT UPDATE(status,published_by,published_at) ON budget_scenario" in text


def test_planning_read_routes_require_all_cost_centers():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/modules/budget/planning_engine_routes.py"
    ).read_text()
    compact = " ".join(source.split())
    assert (
        "ViewSession = Annotated[ BudgetUnitOfWork, "
        "Depends(require_budget(BUDGET_VIEW, all_cost_centers=True)), ]"
        in compact
    )
