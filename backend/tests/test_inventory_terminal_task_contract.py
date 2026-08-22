from __future__ import annotations

import inspect
import io
import tokenize
from uuid import UUID

import pytest

from backend.app.modules.inventory import production


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


def test_terminal_tasks_are_location_bound_without_stock_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(production, "connect", lambda: db)
    monkeypatch.setattr(production, "_assert_runtime_tenant", lambda _db, _principal: None)
    monkeypatch.setattr(production, "_assert_active_device", lambda _db, _principal: None)

    tasks = production.list_terminal_tasks(_Principal())

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
    mission_id = production._terminal_mission_id(
        "tenant-1",
        UUID("22222222-2222-4222-8222-222222222222"),
        "A-04",
    )
    assert mission_id == production._terminal_mission_id(
        "tenant-1",
        UUID("22222222-2222-4222-8222-222222222222"),
        " a-04 ",
    )
    assert mission_id != production._terminal_mission_id(
        "tenant-2",
        UUID("22222222-2222-4222-8222-222222222222"),
        "A-04",
    )
    assert len(mission_id) <= 128


def test_terminal_task_function_does_not_query_stock_truth_tables() -> None:
    rendered = inspect.getsource(production.list_terminal_tasks)
    executable_source = tokenize.untokenize(
        token
        for token in tokenize.generate_tokens(io.StringIO(rendered).readline)
        if token.type != tokenize.COMMENT
    )
    assert "inventory_expected_stock" not in executable_source
    assert "inventory_events" not in executable_source
    assert "expected_quantity" not in executable_source
    assert "unit_cost" not in executable_source
    assert "variance" not in executable_source
