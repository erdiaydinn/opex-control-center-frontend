from __future__ import annotations

import ast
from pathlib import Path

PRODUCTION = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "production.py"


def _reconciliation_source() -> str:
    tree = ast.parse(PRODUCTION.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "reconciliation"
    )
    return ast.unparse(node)


def test_reconciliation_aggregates_only_real_count_events() -> None:
    rendered = _reconciliation_source().replace(" ", "")
    assert "FROMinventory_events" in rendered
    assert "event_typeIN('SCAN','UNEXPECTED_SKU')" in rendered
    assert "GROUPBYbarcode" in rendered


def test_location_completion_can_never_be_stock_reconciliation_input() -> None:
    rendered = _reconciliation_source()
    assert "LOCATION_COMPLETE" not in rendered
    assert "sum(quantity)" in rendered
