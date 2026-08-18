from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ..workforce.active_shift import ActiveShiftAttestation
from . import location_completion_v5 as completion_v5
from . import mission_attempt as mission_attempt_module
from . import production_v5
from .location_completion_v5 import location_completion_hash_input_v5, record_location_completion_v5
from .mission_attempt import abandon_mission_attempt, claim_mission_attempt, mission_claim_hash_input
from .production import InventoryPrincipal, canonical_payload_hash, connect
from .production_v5 import record_event_v5, terminal_event_hash_input_v5, transition_v5
from .reconciliation_v5 import reconciliation_v5
from .service import InventoryRuleError


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryMissionAttemptLeaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tenant = os.getenv("INVENTORY_TEST_TENANT", f"test-{uuid4()}")
        cls.shift_id = "SHIFT-LEASE-CI-1"
        cls.private_one = ec.generate_private_key(ec.SECP256R1())
        cls.private_two = ec.generate_private_key(ec.SECP256R1())
        cls.device_one = uuid4()
        cls.device_two = uuid4()
        with connect() as db:
            for device_id, private_key in (
                (cls.device_one, cls.private_one),
                (cls.device_two, cls.private_two),
            ):
                public_pem = private_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode()
                db.execute(
                    """INSERT INTO inventory_devices(
                         tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                       ) VALUES(%s,%s,'EMP-LEASE',%s,%s,'ACTIVE')""",
                    (cls.tenant, device_id, public_pem, f"mdm-{uuid4()}"),
                )
            db.commit()
        cls.principal_one = InventoryPrincipal(
            cls.tenant,
            "counter-one",
            "EMP-LEASE",
            frozenset({"WH-LEASE"}),
            cls.device_one,
        )
        cls.principal_two = InventoryPrincipal(
            cls.tenant,
            "counter-two",
            "EMP-LEASE",
            frozenset({"WH-LEASE"}),
            cls.device_two,
        )
        attestation = ActiveShiftAttestation(
            tenant_id=cls.tenant,
            employee_id="EMP-LEASE",
            warehouse_id="WH-LEASE",
            shift_id=cls.shift_id,
            attendance_id="ATT-LEASE-CI-1",
            checked_in_at=datetime.now(UTC).isoformat(),
        )
        cls.patches = [
            patch.object(mission_attempt_module, "attest_shift_at_event", return_value=attestation),
            patch.object(production_v5, "attest_shift_at_event", return_value=attestation),
            patch.object(completion_v5, "attest_shift_at_event", return_value=attestation),
        ]
        for item in cls.patches:
            item.start()
            cls.addClassCleanup(item.stop)

    def new_document(self):
        document_id = uuid4()
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by
                   ) VALUES(%s,%s,'WH-LEASE','lease test','COUNTING','maker')""",
                (self.tenant, document_id),
            )
            db.execute(
                "INSERT INTO inventory_document_locations VALUES(%s,%s,'A01')",
                (self.tenant, document_id),
            )
            db.execute(
                """INSERT INTO inventory_expected_stock(
                     tenant_id,document_id,sku,barcode,expected_quantity,unit_cost
                   ) VALUES(%s,%s,'SKU-LEASE','8690000000001',10,5)""",
                (self.tenant, document_id),
            )
            db.commit()
        return document_id

    def sign_hash(self, principal, private_key, payload_hash):
        timestamp = datetime.now(UTC).isoformat()
        nonce = uuid4().hex
        message = f"{principal.device_id}\n{timestamp}\n{nonce}\n{payload_hash}".encode()
        signature = base64.b64encode(
            private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        ).decode()
        return timestamp, nonce, signature

    def claim(self, principal, private_key, document_id, lease_seconds=900):
        payload = {
            "document_id": str(document_id),
            "location_id": "A01",
            "active_shift_id": self.shift_id,
            "lease_seconds": lease_seconds,
        }
        payload["payload_hash"] = canonical_payload_hash(mission_claim_hash_input(payload))
        proof = self.sign_hash(principal, private_key, payload["payload_hash"])
        return claim_mission_attempt(principal, payload, *proof)

    def event(self, principal, private_key, document_id, claim, quantity, occurred_at=None):
        payload = {
            "active_shift_id": self.shift_id,
            "attempt_id": claim["attempt_id"],
            "event_id": str(uuid4()),
            "document_id": str(document_id),
            "lease_id": claim["lease_id"],
            "device_sequence": 1,
            "location_id": "A01",
            "barcode": "8690000000001",
            "quantity": quantity,
            "symbology": "EAN13",
            "occurred_at": occurred_at or datetime.now(UTC).isoformat(),
        }
        payload["payload_hash"] = canonical_payload_hash(terminal_event_hash_input_v5(payload))
        proof = self.sign_hash(principal, private_key, payload["payload_hash"])
        return record_event_v5(principal, payload, *proof)

    def completion(self, principal, private_key, document_id, claim, line_count):
        payload = {
            "active_shift_id": self.shift_id,
            "attempt_id": claim["attempt_id"],
            "confirmed_line_count": line_count,
            "device_sequence": 2,
            "document_id": str(document_id),
            "event_id": str(uuid4()),
            "event_kind": "LOCATION_COMPLETE",
            "lease_id": claim["lease_id"],
            "location_id": "A01",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        payload["payload_hash"] = canonical_payload_hash(location_completion_hash_input_v5(payload))
        proof = self.sign_hash(principal, private_key, payload["payload_hash"])
        return record_location_completion_v5(principal, payload, *proof)

    def test_same_holder_claim_is_idempotent_but_second_terminal_is_blocked(self):
        document_id = self.new_document()
        first = self.claim(self.principal_one, self.private_one, document_id)
        replay = self.claim(self.principal_one, self.private_one, document_id)
        self.assertEqual(first["attempt_id"], replay["attempt_id"])
        self.assertEqual(first["lease_id"], replay["lease_id"])
        self.assertTrue(replay["idempotent_claim"])
        with self.assertRaises(InventoryRuleError):
            self.claim(self.principal_two, self.private_two, document_id)

    def test_event_outside_signed_lease_window_fails_closed(self):
        document_id = self.new_document()
        claim = self.claim(self.principal_one, self.private_one, document_id, lease_seconds=60)
        outside = datetime.fromisoformat(claim["expires_at"]) + timedelta(seconds=1)
        with self.assertRaises(PermissionError):
            self.event(
                self.principal_one,
                self.private_one,
                document_id,
                claim,
                1,
                occurred_at=outside.isoformat(),
            )

    def test_abandoned_attempt_remains_auditable_but_does_not_reconcile(self):
        document_id = self.new_document()
        abandoned = self.claim(self.principal_one, self.private_one, document_id)
        self.event(self.principal_one, self.private_one, document_id, abandoned, 2)
        abandon_mission_attempt(self.principal_one, uuid4() if False else __import__("uuid").UUID(abandoned["attempt_id"]), "device replacement")

        accepted = self.claim(self.principal_two, self.private_two, document_id)
        self.event(self.principal_two, self.private_two, document_id, accepted, 5)
        completion = self.completion(self.principal_two, self.private_two, document_id, accepted, 1)
        self.assertTrue(completion["accepted"])

        result = reconciliation_v5(self.principal_two, document_id)
        row = next(item for item in result["rows"] if item["barcode"] == "8690000000001")
        self.assertEqual(float(row["counted_quantity"]), 5.0)
        statuses = {str(item["attempt_id"]): item["status"] for item in result["attempts"]}
        self.assertEqual(statuses[abandoned["attempt_id"]], "ABANDONED")
        self.assertEqual(statuses[accepted["attempt_id"]], "COMPLETED")

        submitted = transition_v5(
            self.principal_two,
            document_id,
            1,
            "SUBMITTED",
            "completed attempt is authoritative",
        )
        self.assertEqual(submitted["state"], "SUBMITTED")


if __name__ == "__main__":
    unittest.main()
