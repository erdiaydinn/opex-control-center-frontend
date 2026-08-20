from __future__ import annotations

import ast
import json
from pathlib import Path

from backend.app.modules.inventory.location_completion import (
    LOCATION_COMPLETE,
    location_completion_hash_input,
)
from backend.app.modules.inventory.production import canonical_payload_hash

MODULE = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "location_completion.py"
MIGRATION = Path(__file__).parents[1] / "migrations" / "004_inventory_location_completion.sql"
EXPECTED_BODY = (
    '{"active_shift_id":"SHIFT-20260818-001",'
    '"attempt_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
    '"confirmed_line_count":3,"device_sequence":8,'
    '"document_id":"22222222-2222-4222-8222-222222222222",'
    '"event_id":"33333333-3333-4333-8333-333333333333",'
    '"event_kind":"LOCATION_COMPLETE",'
    '"lease_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",'
    '"location_id":"A-04","occurred_at":"2026-08-18T15:05:00Z"}'
)
EXPECTED_HASH = "4a070151035e5a333931d0567f2ad5cb320eaf63a4dbcf44d3cfa7d41a9cab5b"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    return next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_location_completion_hash_contract_is_stable() -> None:
    normalized = location_completion_hash_input(
        {
            "active_shift_id": " SHIFT-20260818-001 ",
            "attempt_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "confirmed_line_count": 3,
            "device_sequence": 8,
            "document_id": "22222222-2222-4222-8222-222222222222",
            "event_id": "33333333-3333-4333-8333-333333333333",
            "lease_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "location_id": " a-04 ",
            "occurred_at": "2026-08-18T15:05:00Z",
        }
    )
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert normalized["event_kind"] == LOCATION_COMPLETE
    assert normalized["confirmed_line_count"] == 3
    assert canonical == EXPECTED_BODY
    assert canonical_payload_hash(normalized) == EXPECTED_HASH


def test_completion_reuses_security_shift_and_historical_lease_authority() -> None:
    rendered = ast.unparse(_function("record_location_completion"))
    assert "_redis_event_preflight" in rendered
    assert "_assert_runtime_tenant" in rendered
    assert "_require_schema_v4" in rendered
    assert "pg_advisory_xact_lock" in rendered
    assert "_verify_device_proof" in rendered
    assert "attest_shift_at_event" in rendered
    assert "attest_event_lease" in rendered
    assert "complete_attempt" in rendered
    assert "active_shift_id" in rendered
    assert "attempt_id" in rendered
    assert "lease_id" in rendered
    assert "confirmed_line_count" in rendered
    assert "LOCATION_COMPLETE" in rendered
    assert "barcode,quantity,symbology" in rendered.replace(" ", "")
    assert "NULL,NULL,NULL" in rendered.replace(" ", "")
    assert "LOCATION_COUNT_COMPLETED" in rendered
    assert "INVENTORY_LOCATION_COMPLETED" in rendered


def test_completion_requires_exact_same_attempt_committed_line_count_including_zero() -> None:
    rendered = ast.unparse(_function("record_location_completion"))
    compact = rendered.replace(" ", "")
    assert "count(*)::integerAScommitted_line_count" in compact
    assert "event_typeIN('SCAN','UNEXPECTED_SKU','RECOUNT')" in compact
    assert "attempt_id=%s" in compact
    assert "occurred_at<=%s" in compact
    assert "committed_line_count!=confirmed_line_count" in compact
    assert "aynı attempt'in server-committed kanıtıyla eşleşmiyor" in rendered


def test_completed_locations_are_removed_from_terminal_queue() -> None:
    rendered = ast.unparse(_function("filter_completed_terminal_tasks"))
    assert "event_type='LOCATION_COMPLETE'" in rendered
    assert "_assert_runtime_tenant" in rendered
    assert "_require_schema_v4" in rendered
    assert "document_id" in rendered
    assert "location_id" in rendered


def test_v4_migration_preserves_real_scan_payloads_and_completion_nulls() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "LOCATION_COMPLETE" in sql
    assert "inventory_location_completion_once_idx" in sql
    assert "barcode IS NULL" in sql
    assert "quantity IS NULL" in sql
    assert "symbology IS NULL" in sql
    assert "event_type<>'LOCATION_COMPLETE'" in sql
    assert "quantity >= 0" in sql
    assert "version,name" in sql
    assert "VALUES (4,'inventory durable location completion')" in sql
