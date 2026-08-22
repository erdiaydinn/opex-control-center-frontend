from __future__ import annotations

import base64
from datetime import UTC, datetime
import os
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ..workforce.active_shift import ActiveShiftAttestation
from . import location_completion as location_completion_module
from . import mission_event as mission_event_module
from .location_completion import location_completion_hash_input, record_location_completion
from .mission_event import record_event, terminal_event_hash_input
from .mission_lease import claim_terminal_mission, mission_claim_hash_input, supersede_attempt
from .production import InventoryPrincipal, canonical_payload_hash, connect
from .reconciliation import reconciliation


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryHistoricalSupersedeReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenant = os.getenv("INVENTORY_TEST_TENANT", f"test-{uuid4()}")
        self.document_id = uuid4()
        self.location_id = "A01"
        self.old_device = uuid4()
        self.new_device = uuid4()
        self.old_key = ec.generate_private_key(ec.SECP256R1())
        self.new_key = ec.generate_private_key(ec.SECP256R1())
        self.old_shift = "SHIFT-HISTORICAL-OLD"
        self.new_shift = "SHIFT-HISTORICAL-NEW"
        self.old_principal = InventoryPrincipal(
            self.tenant,
            "old-counter",
            "EMP-HIST-OLD",
            frozenset({"WH-1"}),
            self.old_device,
        )
        self.new_principal = InventoryPrincipal(
            self.tenant,
            "supervisor-counter",
            "EMP-HIST-NEW",
            frozenset({"WH-1"}),
            self.new_device,
        )
        with connect() as db:
            for principal, private_key in (
                (self.old_principal, self.old_key),
                (self.new_principal, self.new_key),
            ):
                public_pem = private_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode()
                db.execute(
                    """INSERT INTO inventory_devices(
                         tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                       ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                    (
                        self.tenant,
                        principal.device_id,
                        principal.employee_id,
                        public_pem,
                        f"mdm-{uuid4()}",
                    ),
                )
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by
                   ) VALUES(%s,%s,'WH-1','Historical supersede replay','COUNTING','maker')""",
                (self.tenant, self.document_id),
            )
            db.execute(
                "INSERT INTO inventory_document_locations VALUES(%s,%s,%s)",
                (self.tenant, self.document_id, self.location_id),
            )
            db.execute(
                """INSERT INTO inventory_expected_stock(
                     tenant_id,document_id,sku,barcode,expected_quantity,unit_cost
                   ) VALUES(%s,%s,'SKU-1','8690000000001',10,12.5)""",
                (self.tenant, self.document_id),
            )
            db.commit()

    def _key(self, principal: InventoryPrincipal):
        if principal.device_id == self.old_device:
            return self.old_key
        if principal.device_id == self.new_device:
            return self.new_key
        raise AssertionError("unknown test principal")

    def _sign_hash(self, principal: InventoryPrincipal, payload_hash: str):
        timestamp = datetime.now(UTC).isoformat()
        nonce = uuid4().hex
        message = f"{principal.device_id}\n{timestamp}\n{nonce}\n{payload_hash}".encode()
        signature = base64.b64encode(
            self._key(principal).sign(message, ec.ECDSA(hashes.SHA256()))
        ).decode()
        return timestamp, nonce, signature

    def _attestation(
        self,
        principal: InventoryPrincipal,
        shift_id: str,
    ) -> ActiveShiftAttestation:
        return ActiveShiftAttestation(
            tenant_id=self.tenant,
            employee_id=principal.employee_id,
            warehouse_id="WH-1",
            shift_id=shift_id,
            attendance_id=f"ATT-{principal.employee_id}",
            checked_in_at=datetime.now(UTC).isoformat(),
        )

    def _claim(self, principal: InventoryPrincipal, shift_id: str) -> dict:
        payload = {
            "document_id": str(self.document_id),
            "location_id": self.location_id,
        }
        payload["payload_hash"] = canonical_payload_hash(
            mission_claim_hash_input(self.document_id, self.location_id)
        )
        timestamp, nonce, signature = self._sign_hash(principal, payload["payload_hash"])
        return claim_terminal_mission(
            principal,
            shift_id,
            payload,
            timestamp,
            nonce,
            signature,
        )

    def _event_payload(
        self,
        claim: dict,
        principal: InventoryPrincipal,
        shift_id: str,
        *,
        quantity: int,
        sequence: int,
        occurred_at: datetime,
    ) -> dict:
        payload = {
            "active_shift_id": shift_id,
            "attempt_id": claim["attempt_id"],
            "event_id": str(uuid4()),
            "document_id": str(self.document_id),
            "lease_id": claim["lease_id"],
            "device_sequence": sequence,
            "location_id": self.location_id,
            "barcode": "8690000000001",
            "quantity": quantity,
            "symbology": "EAN13",
            "occurred_at": occurred_at.isoformat(),
        }
        payload["payload_hash"] = canonical_payload_hash(terminal_event_hash_input(payload))
        return payload

    def _upload_event(
        self,
        principal: InventoryPrincipal,
        shift_id: str,
        payload: dict,
    ) -> dict:
        timestamp, nonce, signature = self._sign_hash(principal, payload["payload_hash"])
        with patch.object(
            mission_event_module,
            "attest_shift_at_event",
            return_value=self._attestation(principal, shift_id),
        ):
            return record_event(principal, payload, timestamp, nonce, signature)

    def _complete_new_attempt(self, claim: dict) -> dict:
        completed_at = datetime.now(UTC)
        payload = {
            "active_shift_id": self.new_shift,
            "attempt_id": claim["attempt_id"],
            "confirmed_line_count": 1,
            "device_sequence": 2,
            "document_id": str(self.document_id),
            "event_id": str(uuid4()),
            "event_kind": "LOCATION_COMPLETE",
            "lease_id": claim["lease_id"],
            "location_id": self.location_id,
            "occurred_at": completed_at.isoformat(),
        }
        payload["payload_hash"] = canonical_payload_hash(location_completion_hash_input(payload))
        timestamp, nonce, signature = self._sign_hash(
            self.new_principal,
            payload["payload_hash"],
        )
        with patch.object(
            location_completion_module,
            "attest_shift_at_event",
            return_value=self._attestation(self.new_principal, self.new_shift),
        ):
            return record_location_completion(
                self.new_principal,
                payload,
                timestamp,
                nonce,
                signature,
            )

    def test_delayed_pre_supersede_event_is_preserved_but_excluded_from_truth(self) -> None:
        old_claim = self._claim(self.old_principal, self.old_shift)
        # The physical count happened while the old immutable lease was valid, but
        # network loss prevents upload until after a governed reassignment.
        delayed_payload = self._event_payload(
            old_claim,
            self.old_principal,
            self.old_shift,
            quantity=2,
            sequence=1,
            occurred_at=datetime.now(UTC),
        )

        reassigned = supersede_attempt(
            self.new_principal,
            self.document_id,
            self.location_id,
            "managed device replacement",
        )
        self.assertEqual(reassigned["superseded_attempt_id"], old_claim["attempt_id"])

        delayed_result = self._upload_event(
            self.old_principal,
            self.old_shift,
            delayed_payload,
        )
        self.assertTrue(delayed_result["accepted"])
        self.assertEqual(delayed_result["attempt_id"], old_claim["attempt_id"])

        with connect() as db:
            old_attempt = db.execute(
                """SELECT state FROM inventory_mission_attempts
                   WHERE tenant_id=%s AND attempt_id=%s""",
                (self.tenant, UUID(old_claim["attempt_id"])),
            ).fetchone()
            old_evidence = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_events
                   WHERE tenant_id=%s AND event_id=%s AND attempt_id=%s""",
                (
                    self.tenant,
                    UUID(delayed_payload["event_id"]),
                    UUID(old_claim["attempt_id"]),
                ),
            ).fetchone()
        self.assertEqual(old_attempt["state"], "SUPERSEDED")
        self.assertEqual(old_evidence["n"], 1)

        new_claim = self._claim(self.new_principal, self.new_shift)
        self.assertNotEqual(new_claim["attempt_id"], old_claim["attempt_id"])
        new_payload = self._event_payload(
            new_claim,
            self.new_principal,
            self.new_shift,
            quantity=5,
            sequence=1,
            occurred_at=datetime.now(UTC),
        )
        self.assertTrue(
            self._upload_event(self.new_principal, self.new_shift, new_payload)["accepted"]
        )
        self.assertTrue(self._complete_new_attempt(new_claim)["accepted"])

        rows = reconciliation(self.new_principal, self.document_id)["rows"]
        sku_row = next(row for row in rows if row["barcode"] == "8690000000001")
        self.assertEqual(float(sku_row["counted_quantity"]), 5.0)


if __name__ == "__main__":
    unittest.main()
