from __future__ import annotations

import base64
from datetime import UTC, datetime
import os
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .production import (
    InventoryPrincipal,
    canonical_payload_hash,
    connect,
    record_event,
    terminal_event_hash_input,
    transition,
)
from .service import InventoryRuleError


class InventoryProductionContractTests(unittest.TestCase):
    def test_canonical_hash_is_order_independent(self):
        self.assertEqual(canonical_payload_hash({"b": 2, "a": 1}), canonical_payload_hash({"a": 1, "b": 2}))

    def test_principal_requires_all_authoritative_scopes(self):
        principal = InventoryPrincipal("tenant", "subject", "employee", frozenset(), uuid4())
        with self.assertRaises(InventoryRuleError):
            principal.validate()


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryPostgresAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tenant = os.getenv("INVENTORY_TEST_TENANT", f"test-{uuid4()}")
        cls.document_id = uuid4()
        cls.device_id = uuid4()
        cls.private_key = ec.generate_private_key(ec.SECP256R1())
        public_pem = cls.private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_devices(
                     tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                   ) VALUES(%s,%s,'EMP-1',%s,%s,'ACTIVE')""",
                (cls.tenant, cls.device_id, public_pem, f"mdm-{uuid4()}"),
            )
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by
                   ) VALUES(%s,%s,'WH-1','P0 test','COUNTING','maker')""",
                (cls.tenant, cls.document_id),
            )
            db.execute(
                "INSERT INTO inventory_document_locations VALUES(%s,%s,'A01')",
                (cls.tenant, cls.document_id),
            )
            db.execute(
                """INSERT INTO inventory_expected_stock(
                     tenant_id,document_id,sku,barcode,expected_quantity,unit_cost
                   ) VALUES(%s,%s,'SKU-1','8690000000001',10,12.5)""",
                (cls.tenant, cls.document_id),
            )
            db.commit()
        cls.principal = InventoryPrincipal(
            cls.tenant, "maker", "EMP-1", frozenset({"WH-1"}), cls.device_id,
        )

    def signed_event(self, *, event_id=None, sequence=1, barcode="8690000000001"):
        payload = {
            "event_id": str(event_id or uuid4()),
            "document_id": str(self.document_id),
            "device_sequence": sequence,
            "location_id": "A01",
            "barcode": barcode,
            "quantity": 2,
            "symbology": "EAN13",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        payload["payload_hash"] = canonical_payload_hash(terminal_event_hash_input(payload))
        timestamp = datetime.now(UTC).isoformat()
        nonce = uuid4().hex
        message = f"{self.device_id}\n{timestamp}\n{nonce}\n{payload['payload_hash']}".encode()
        signature = base64.b64encode(self.private_key.sign(message, ec.ECDSA(hashes.SHA256()))).decode()
        return payload, timestamp, nonce, signature

    def test_exact_replay_payload_substitution_and_unexpected_sku(self):
        event_id = uuid4()
        payload, timestamp, nonce, signature = self.signed_event(event_id=event_id)
        first = record_event(self.principal, payload, timestamp, nonce, signature)
        replay = record_event(self.principal, payload, timestamp, nonce, signature)
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])

        changed = dict(payload, quantity=3)
        changed["payload_hash"] = canonical_payload_hash(terminal_event_hash_input(changed))
        with self.assertRaises(InventoryRuleError):
            record_event(self.principal, changed, timestamp, uuid4().hex, signature)

        unexpected, ts2, nonce2, sig2 = self.signed_event(sequence=2, barcode="9999999999999")
        self.assertEqual(record_event(self.principal, unexpected, ts2, nonce2, sig2)["event_type"], "UNEXPECTED_SKU")

    def test_concurrent_duplicate_event_is_exactly_once(self):
        payload, timestamp, nonce, signature = self.signed_event(sequence=20)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda _: record_event(self.principal, payload, timestamp, nonce, signature),
                range(2),
            ))
        self.assertEqual({row["event_id"] for row in results}, {payload["event_id"]})
        self.assertEqual(sorted(row["idempotent_replay"] for row in results), [False, True])
        with connect() as db:
            count = db.execute(
                "SELECT count(*) AS n FROM inventory_events WHERE tenant_id=%s AND event_id=%s",
                (self.tenant, payload["event_id"]),
            ).fetchone()["n"]
        self.assertEqual(count, 1)

    def test_maker_checker_and_stale_supervisor_revision(self):
        submitted = transition(self.principal, self.document_id, 1, "SUBMITTED", "count complete")
        self.assertEqual(submitted["revision"], 2)
        with self.assertRaises(InventoryRuleError):
            transition(self.principal, self.document_id, 2, "APPROVED", "self approval")
        checker = InventoryPrincipal(self.tenant, "checker", "EMP-2", frozenset({"WH-1"}), self.device_id)
        approved = transition(checker, self.document_id, 2, "APPROVED", "variance reviewed")
        self.assertEqual(approved["revision"], 3)
        with self.assertRaises(InventoryRuleError):
            transition(checker, self.document_id, 2, "LOCKED", "stale screen")

    def test_load_smoke_preserves_all_distinct_events(self):
        signed = [self.signed_event(sequence=100 + index) for index in range(40)]
        started = perf_counter()
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda args: record_event(self.principal, *args), signed))
        elapsed = perf_counter() - started
        self.assertEqual(len({row["event_id"] for row in results}), 40)
        self.assertTrue(all(row["accepted"] for row in results))
        self.assertLess(elapsed, 20, "CI smoke only; this is not production capacity acceptance")


if __name__ == "__main__":
    unittest.main()
