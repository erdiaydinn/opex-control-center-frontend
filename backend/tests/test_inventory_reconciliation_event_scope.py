from __future__ import annotations

import ast
from pathlib import Path

RECONCILIATION = (
    Path(__file__).parents[1]
    / "app"
    / "modules"
    / "inventory"
    / "reconciliation.py"
)


def _reconciliation_source() -> str:
    tree = ast.parse(RECONCILIATION.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "reconciliation"
    )
    return ast.unparse(node)


def test_reconciliation_aggregates_only_real_count_events() -> None:
    rendered = _reconciliation_source().replace(" ", "")
    assert "FROMinventory_eventse" in rendered
    assert "event_typeIN('SCAN','UNEXPECTED_SKU','RECOUNT')" in rendered
    assert "GROUPBYbarcode" in rendered
    assert "count_version_rank=1" in rendered


def test_location_completion_can_never_be_stock_reconciliation_input() -> None:
    rendered = _reconciliation_source()
    assert "LOCATION_COMPLETE" not in rendered
    assert "sum(quantity)" in rendered


def test_expected_stock_is_scoped_before_barcode_join() -> None:
    rendered = _reconciliation_source().replace(" ", "")
    assert "WITHexpectedAS(" in rendered
    assert "FROMinventory_expected_stock" in rendered
    assert "WHEREtenant_id=%sANDdocument_id=%s" in rendered
    assert "FROMexpecteds" in rendered
    assert "FULLOUTERJOINcountedcONc.barcode=s.barcode" in rendered
    assert "FROMinventory_expected_stocks\nFULLOUTERJOIN" not in rendered


def test_reconciliation_is_tenant_and_warehouse_authorized() -> None:
    rendered = _reconciliation_source()
    assert "inventory_current_tenant" in rendered
    assert "principal.tenant_id" in rendered
    assert "principal.warehouse_scope" in rendered
