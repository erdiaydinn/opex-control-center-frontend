from __future__ import annotations

import json
from decimal import Decimal

from backend.app.modules.inventory.mission_event import terminal_event_hash_input
from backend.app.modules.inventory.production import canonical_payload_hash

EXPECTED_BODY = (
    '{"active_shift_id":"SHIFT-20260818-001",'
    '"attempt_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
    '"barcode":"8690000000001","device_sequence":7,'
    '"document_id":"22222222-2222-4222-8222-222222222222",'
    '"event_id":"11111111-1111-4111-8111-111111111111",'
    '"lease_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",'
    '"location_id":"A-04","occurred_at":"2026-08-18T15:00:00Z",'
    '"quantity":"5","symbology":"EAN13"}'
)
EXPECTED_HASH = "7ea0134fc401ec93770b492ecd423dd0644df1f79d153c4b6f58ad2ed62489e5"


def test_terminal_event_hash_contract_matches_android_golden_vector() -> None:
    normalized = terminal_event_hash_input(
        {
            "active_shift_id": " SHIFT-20260818-001 ",
            "attempt_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "barcode": " 8690000000001 ",
            "device_sequence": 7,
            "document_id": "22222222-2222-4222-8222-222222222222",
            "event_id": "11111111-1111-4111-8111-111111111111",
            "lease_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
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
