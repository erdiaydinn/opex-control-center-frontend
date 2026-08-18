from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID

PRODUCTION = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "production.py"
EXPECTED_BODY = (
    '{"barcode":"8690000000001","device_sequence":7,'
    '"document_id":"22222222-2222-4222-8222-222222222222",'
    '"event_id":"11111111-1111-4111-8111-111111111111",'
    '"location_id":"A-04","occurred_at":"2026-08-18T15:00:00Z",'
    '"quantity":"5","symbology":"EAN13"}'
)
EXPECTED_HASH = "83fa7ef91803244218d6851f0ed217f66d9641d46e419fad79eb0b749c1dc291"


def _load_hash_contract():
    tree = ast.parse(PRODUCTION.read_text(encoding="utf-8"))
    names = {"canonical_payload_hash", "terminal_event_hash_input"}
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in functions} == names
    namespace = {
        "Decimal": Decimal,
        "UUID": UUID,
        "hashlib": hashlib,
        "json": json,
    }
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(PRODUCTION), "exec"), namespace)
    return namespace["terminal_event_hash_input"], namespace["canonical_payload_hash"]


def test_terminal_event_hash_contract_matches_android_golden_vector() -> None:
    terminal_event_hash_input, canonical_payload_hash = _load_hash_contract()
    normalized = terminal_event_hash_input(
        {
            "barcode": " 8690000000001 ",
            "device_sequence": 7,
            "document_id": "22222222-2222-4222-8222-222222222222",
            "event_id": "11111111-1111-4111-8111-111111111111",
            "location_id": " a-04 ",
            "occurred_at": "2026-08-18T15:00:00Z",
            "quantity": Decimal("5.000"),
            "symbology": " EAN13 ",
        }
    )
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert canonical == EXPECTED_BODY
    assert canonical_payload_hash(normalized) == EXPECTED_HASH
