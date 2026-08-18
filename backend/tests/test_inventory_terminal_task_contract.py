from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

PRODUCTION = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "production.py"


def _load_task_contract():
    tree = ast.parse(PRODUCTION.read_text(encoding="utf-8"))
    names = {"_terminal_mission_id", "list_terminal_tasks"}
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in functions} == names
    namespace: dict[str, object] = {
        "Any": Any,
        "UUID": UUID,
        "InventoryPrincipal": object,
        "hashlib": hashlib,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(PRODUCTION), "exec"), namespace)
    return namespace, tree


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self._rows = rows
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return _Rows(self._rows)


class _Principal:
    tenant_id = "tenant-1"
    device_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    employee_id = "employee-1"
    warehouse_scope = frozenset({"FULYA"})

    def validate(self):
        return None


def test_terminal_tasks_are_location_bound_without_stock_truth() -> None:
    namespace, _ = _load_task_contract()
    rows = [
        {
            "id": UUID("22222222-2222-4222-8222-222222222222"),
            "warehouse_id": "FULYA",
            "name": "Weekly count",
            "state": "COUNTING",
            "revision": 3,
            "updated_at": "2026-08-18T15:00:00Z",
            "location_id": " a-04 ",
            "location_count": 2,
        },
        {
            "id": UUID("22222222-2222-4222-8222-222222222222"),
            "warehouse_id": "FULYA",
            "name": "Weekly count",
            "state": "COUNTING",
            "revision": 3,
            "updated_at": "2026-08-18T15:00:00Z",
            "location_id": "B-05",
            "location_count": 2,
        },
    ]
    db = _Db(rows)
    namespace.update(
        {
            "connect": lambda: db,
            "_assert_runtime_tenant": lambda _db, _principal: None,
            "_assert_active_device": lambda _db, _principal: None,
        }
    )

    tasks = namespace["list_terminal_tasks"](_Principal())

    assert len(tasks) == 2
    assert tasks[0]["location_id"] == "A-04"
    assert tasks[1]["location_id"] == "B-05"
    assert tasks[0]["location_count"] == 2
    assert tasks[0]["operation"] == "inventory.count"
    assert tasks[0]["runtime_profile"] == "EAY_TERMINAL"
    assert tasks[0]["mission_id"] != tasks[1]["mission_id"]
    assert tasks[0]["mission_id"].startswith("inventory.count:")
    forbidden = {"expected_quantity", "unit_cost", "sku", "variance", "variance_value"}
    assert not forbidden.intersection(tasks[0])
    assert "inventory_expected_stock" not in db.sql
    assert "inventory_events" not in db.sql


def test_terminal_task_mission_id_is_stable_and_tenant_bound() -> None:
    namespace, _ = _load_task_contract()
    mission_id = namespace["_terminal_mission_id"](
        "tenant-1",
        UUID("22222222-2222-4222-8222-222222222222"),
        "A-04",
    )
    assert mission_id == namespace["_terminal_mission_id"](
        "tenant-1",
        UUID("22222222-2222-4222-8222-222222222222"),
        " a-04 ",
    )
    assert mission_id != namespace["_terminal_mission_id"](
        "tenant-2",
        UUID("22222222-2222-4222-8222-222222222222"),
        "A-04",
    )
    assert len(mission_id) <= 128


def test_terminal_task_function_does_not_query_stock_truth_tables() -> None:
    _, tree = _load_task_contract()
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "list_terminal_tasks"
    )
    rendered = ast.unparse(function)
    assert "inventory_expected_stock" not in rendered
    assert "inventory_events" not in rendered
    assert "expected_quantity" not in rendered
    assert "unit_cost" not in rendered
    assert "variance" not in rendered
