from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import os
from threading import Lock
from time import perf_counter
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
from .mission_lease import (
    claim_terminal_mission,
    mission_claim_hash_input,
    supersede_attempt,
)
from .production import InventoryPrincipal, canonical_payload_hash, connect, transition
from .reconciliation import reconciliation
from .service import InventoryRuleError


class InventoryProductionContractTests(unittest.TestCase):
    def test_canonical_hash_is_order_independent(self):
        self.assertEqual(
            canonical_payload_hash({"b": 2, "a": 1}),
            canonical_payload_hash({"a": 1, "b": 2}),
        )

    def test_principal_requires_all_authoritative_scopes(self):
        principal = InventoryPrincipal("tenant", "subject", "employee", frozenset(), uuid4())
        with self.assertRaises(InventoryRuleError):
            principal.validate()


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryPostgresAdversarialTests(unittest.TestCase):
    _sequence_lock = Lock()
    _sequences: dict[UUID, int] = {}

    @classmethod
    def setUpClass(cls):
        cls.tenant = os.getenv("INVENTORY_TEST_TENANT", f"test-{uuid4()}")
        cls.device_one = uuid4()
        cls.device_two = uuid4()
        cls.private_key_one = ec.generate_private_key(ec.SECP256R1())
        cls.private_key_two = ec.generate_private_key(ec.SECP256R1())
        cls.shift_one = "SHIFT-INVENTORY-CI-1"
        cls.shift_two = "SHIFT-INVENTORY-CI-2"
        cls.principal_one = InventoryPrincipal(
            cls.tenant,
            "maker",
            "EMP-1",
            frozenset({"WH-1"}),
            cls.device_one,
        )
        cls.principal_two = InventoryPrincipal(
            cls.tenant,
            "checker",
            "EMP-2",
            frozenset({"WH-1"}),
            cls.device_two,
        )
        with connect() as db:
            for device_id, employee_id, private_key in (
                (cls.device_one, "EMP-1", cls.private_key_one),
                (cls.device_two, "EMP-2", cls.private_key_two),
            ):
                public_pem = private_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode()
                db.execute(
                    """INSERT INTO inventory_devices(
                         tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                       ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                    (cls.tenant, device_id, employee_id, public_pem, f"mdm-{uuid4()}"),
                )
            db.commit()
        cls._sequences = {cls.device_one: 0, cls.device_two: 0}

    def setUp(self):
        self.document_id = uuid4()
        self.location_id = "A01"
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by
                   ) VALUES(%s,%s,'WH-1','P0 mission lease test','COUNTING','maker')""",
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

    @classmethod
    def next_sequence(cls, principal: InventoryPrincipal) -> int:
        with cls._sequence_lock:
            cls._sequences[principal.device_id] += 1
            return cls._sequences[principal.device_id]

    @staticmethod
    def attestation(principal: InventoryPrincipal, shift_id: str) -> ActiveShiftAttestation:
        return ActiveShiftAttestation(
            tenant_id=principal.tenant_id,
            employee_id=principal.employee_id,
            warehouse_id="WH-1",
            shift_id=shift_id,
            attendance_id=f"ATT-{principal.employee_id}",
            checked_in_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        )

    @staticmethod
    def key_for(principal: InventoryPrincipal):
        if principal.employee_id == "EMP-1":
            return InventoryPostgresAdversarialTests.private_key_one
        if principal.employee_id == "EMP-2":
            return InventoryPostgresAdversarialTests.private_key_two
        raise AssertionError("unknown test principal")

    def sign_hash(self, principal: InventoryPrincipal, payload_hash: str):
        timestamp = datetime.now(UTC).isoformat()
        nonce = uuid4().hex
        message = f"{principal.device_id}\n{timestamp}\n{nonce}\n{payload_hash}".encode()
        signature = base64.b64encode(
            self.key_for(principal).sign(message, ec.ECDSA(hashes.SHA256()))
        ).decode()
        return timestamp, nonce, signature

    def claim(self, principal=None, shift_id=None):
        principal = principal or self.principal_one
        shift_id = shift_id or self.shift_one
        payload = {
            "document_id": str(self.document_id),
            "location_id": self.location_id,
        }
        payload["payload_hash"] = canonical_payload_hash(
            mission_claim_hash_input(self.document_id, self.location_id)
        )
        timestamp, nonce, signature = self.sign_hash(principal, payload["payload_hash"])
        return claim_terminal_mission(
            principal,
            shift_id,
            payload,
            timestamp,
            nonce,
            signature,
        )

    def signed_event(
        self,
        claim,
        *,
        principal=None,
        shift_id=None,
        event_id=None,
        barcode="8690000000001",
        quantity=2,
        occurred_at=None,
    ):
        principal = principal or self.principal_one
        shift_id = shift_id or self.shift_one
        payload = {
            "active_shift_id": shift_id,
            "attempt_id": claim["attempt_id"],
            "event_id": str(event_id or uuid4()),
            "document_id": str(self.document_id),
            "lease_id": claim["lease_id"],
            "device_sequence": self.next_sequence(principal),
            "location_id": self.location_id,
            "barcode": barcode,
            "quantity": quantity,
            "symbology": "EAN13",
            "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
        }
        payload["payload_hash"] = canonical_payload_hash(terminal_event_hash_input(payload))
        timestamp, nonce, signature = self.sign_hash(principal, payload["payload_hash"])
        return payload, timestamp, nonce, signature

    def record_signed_event(self, claim, **kwargs):
        principal = kwargs.pop("principal", self.principal_one)
        shift_id = kwargs.pop("shift_id", self.shift_one)
        signed = self.signed_event(
            claim,
            principal=principal,
            shift_id=shift_id,
            **kwargs,
        )
        with patch.object(
            mission_event_module,
            "attest_shift_at_event",
            return_value=self.attestation(principal, shift_id),
        ):
            return record_event(principal, *signed)

    def signed_completion(self, claim, *, principal=None, shift_id=None, occurred_at=None):
        principal = principal or self.principal_one
        shift_id = shift_id or self.shift_one
        completed_at = occurred_at or datetime.now(UTC)
        with connect() as db:
            row = db.execute(
                """SELECT count(*)::integer AS line_count
                   FROM inventory_events
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s
                     AND attempt_id=%s
                     AND event_type IN ('SCAN','UNEXPECTED_SKU')
                     AND occurred_at<=%s""",
                (
                    self.tenant,
                    self.document_id,
                    self.location_id,
                    UUID(claim["attempt_id"]),
                    completed_at,
                ),
            ).fetchone()
        payload = {
            "active_shift_id": shift_id,
            "attempt_id": claim["attempt_id"],
            "confirmed_line_count": int(row["line_count"]),
            "device_sequence": self.next_sequence(principal),
            "document_id": str(self.document_id),
            "event_id": str(uuid4()),
            "event_kind": "LOCATION_COMPLETE",
            "lease_id": claim["lease_id"],
            "location_id": self.location_id,
            "occurred_at": completed_at.isoformat(),
        }
        payload["payload_hash"] = canonical_payload_hash(location_completion_hash_input(payload))
        timestamp, nonce, signature = self.sign_hash(principal, payload["payload_hash"])
        return payload, timestamp, nonce, signature

    def record_completion(self, claim, *, principal=None, shift_id=None, occurred_at=None):
        principal = principal or self.principal_one
        shift_id = shift_id or self.shift_one
        signed = self.signed_completion(
            claim,
            principal=principal,
            shift_id=shift_id,
            occurred_at=occurred_at,
        )
        with patch.object(
            location_completion_module,
            "attest_shift_at_event",
            return_value=self.attestation(principal, shift_id),
        ):
            return record_location_completion(principal, *signed)

    def create_historical_lease(self, *, valid_from, valid_until):
        attempt_id = uuid4()
        lease_id = uuid4()
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_mission_attempts(
                     tenant_id,attempt_id,document_id,warehouse_id,location_id,
                     created_by_subject,created_by_employee_id,created_at
                   ) VALUES(%s,%s,%s,'WH-1',%s,%s,%s,%s)""",
                (
                    self.tenant,
                    attempt_id,
                    self.document_id,
                    self.location_id,
                    self.principal_one.subject,
                    self.principal_one.employee_id,
                    valid_from - timedelta(minutes=1),
                ),
            )
            db.execute(
                """INSERT INTO inventory_mission_leases(
                     tenant_id,lease_id,attempt_id,employee_id,device_id,shift_id,
                     warehouse_id,valid_from,valid_until,issued_at
                   ) VALUES(%s,%s,%s,%s,%s,%s,'WH-1',%s,%s,%s)""",
                (
                    self.tenant,
                    lease_id,
                    attempt_id,
                    self.principal_one.employee_id,
                    self.principal_one.device_id,
                    self.shift_one,
                    valid_from,
                    valid_until,
                    valid_from,
                ),
            )
            db.commit()
        return {
            "attempt_id": str(attempt_id),
            "lease_id": str(lease_id),
        }

    def test_same_device_claim_retry_is_idempotent(self):
        first = self.claim()
        replay = self.claim()
        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(first["attempt_id"], replay["attempt_id"])
        self.assertEqual(first["lease_id"], replay["lease_id"])

    def test_two_terminals_cannot_claim_same_location_concurrently(self):
        def attempt(principal, shift_id):
            try:
                return ("ok", self.claim(principal, shift_id))
            except InventoryRuleError as error:
                return ("blocked", str(error))

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda args: attempt(*args),
                    (
                        (self.principal_one, self.shift_one),
                        (self.principal_two, self.shift_two),
                    ),
                )
            )
        self.assertEqual(sorted(result[0] for result in results), ["blocked", "ok"])
        with connect() as db:
            active_attempts = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_mission_attempts
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s AND state='ACTIVE'""",
                (self.tenant, self.document_id, self.location_id),
            ).fetchone()["n"]
            live_leases = db.execute(
                """SELECT count(*)::integer AS n
                   FROM inventory_mission_leases l
                   LEFT JOIN inventory_mission_lease_closures c
                     ON c.tenant_id=l.tenant_id AND c.lease_id=l.lease_id
                   WHERE l.tenant_id=%s AND l.attempt_id IN (
                     SELECT attempt_id FROM inventory_mission_attempts
                     WHERE tenant_id=%s AND document_id=%s AND location_id=%s
                   ) AND c.lease_id IS NULL AND l.valid_until>now()""",
                (self.tenant, self.tenant, self.document_id, self.location_id),
            ).fetchone()["n"]
        self.assertEqual(active_attempts, 1)
        self.assertEqual(live_leases, 1)

    def test_exact_replay_payload_substitution_and_unexpected_sku(self):
        claim = self.claim()
        event_id = uuid4()
        signed = self.signed_event(claim, event_id=event_id)
        with patch.object(
            mission_event_module,
            "attest_shift_at_event",
            return_value=self.attestation(self.principal_one, self.shift_one),
        ):
            first = record_event(self.principal_one, *signed)
            replay = record_event(self.principal_one, *signed)
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(first["active_shift_id"], self.shift_one)
        self.assertEqual(first["attempt_id"], claim["attempt_id"])
        self.assertEqual(first["lease_id"], claim["lease_id"])

        payload, timestamp, _nonce, signature = signed
        changed = dict(payload, quantity=3)
        changed["payload_hash"] = canonical_payload_hash(terminal_event_hash_input(changed))
        with self.assertRaises(InventoryRuleError):
            record_event(self.principal_one, changed, timestamp, uuid4().hex, signature)

        unexpected = self.record_signed_event(claim, barcode="9999999999999")
        self.assertEqual(unexpected["event_type"], "UNEXPECTED_SKU")

    def test_concurrent_duplicate_event_is_exactly_once(self):
        claim = self.claim()
        signed = self.signed_event(claim)
        attestation = self.attestation(self.principal_one, self.shift_one)
        with patch.object(mission_event_module, "attest_shift_at_event", return_value=attestation):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda _: record_event(self.principal_one, *signed),
                        range(2),
                    )
                )
        payload = signed[0]
        self.assertEqual({row["event_id"] for row in results}, {payload["event_id"]})
        self.assertEqual(sorted(row["idempotent_replay"] for row in results), [False, True])
        with connect() as db:
            count = db.execute(
                "SELECT count(*) AS n FROM inventory_events WHERE tenant_id=%s AND event_id=%s",
                (self.tenant, payload["event_id"]),
            ).fetchone()["n"]
        self.assertEqual(count, 1)

    def test_valid_offline_event_may_upload_after_lease_expiry(self):
        valid_from = datetime.now(UTC) - timedelta(minutes=30)
        valid_until = datetime.now(UTC) - timedelta(minutes=20)
        claim = self.create_historical_lease(valid_from=valid_from, valid_until=valid_until)
        occurred_at = valid_from + timedelta(minutes=5)
        result = self.record_signed_event(claim, occurred_at=occurred_at)
        self.assertTrue(result["accepted"])

    def test_renewal_cannot_retroactively_authorize_a_past_gap(self):
        first_from = datetime.now(UTC) - timedelta(minutes=30)
        first_until = datetime.now(UTC) - timedelta(minutes=20)
        claim = self.create_historical_lease(valid_from=first_from, valid_until=first_until)
        second_from = datetime.now(UTC) - timedelta(minutes=10)
        second_until = datetime.now(UTC) + timedelta(minutes=5)
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_mission_leases(
                     tenant_id,lease_id,attempt_id,employee_id,device_id,shift_id,
                     warehouse_id,valid_from,valid_until
                   ) VALUES(%s,%s,%s,%s,%s,%s,'WH-1',%s,%s)""",
                (
                    self.tenant,
                    uuid4(),
                    UUID(claim["attempt_id"]),
                    self.principal_one.employee_id,
                    self.principal_one.device_id,
                    self.shift_one,
                    second_from,
                    second_until,
                ),
            )
            db.commit()
        gap_time = datetime.now(UTC) - timedelta(minutes=15)
        with self.assertRaises(PermissionError):
            self.record_signed_event(claim, occurred_at=gap_time)

    def test_superseded_attempt_evidence_is_excluded_from_reconciliation(self):
        old_claim = self.claim()
        self.record_signed_event(old_claim, quantity=2)
        reassigned = supersede_attempt(
            self.principal_two,
            self.document_id,
            self.location_id,
            "device replacement",
        )
        self.assertEqual(reassigned["superseded_attempt_id"], old_claim["attempt_id"])

        new_claim = self.claim()
        self.assertNotEqual(new_claim["attempt_id"], old_claim["attempt_id"])
        self.record_signed_event(new_claim, quantity=5)
        completion = self.record_completion(new_claim)
        self.assertTrue(completion["accepted"])

        rows = reconciliation(self.principal_two, self.document_id)["rows"]
        sku_row = next(row for row in rows if row["barcode"] == "8690000000001")
        self.assertEqual(float(sku_row["counted_quantity"]), 5.0)

    def test_maker_checker_requires_completion_and_reconciliation(self):
        claim = self.claim()
        self.record_signed_event(claim, quantity=4)
        completion = self.record_completion(claim)
        self.assertTrue(completion["accepted"])
        self.assertEqual(completion["active_shift_id"], self.shift_one)
        self.assertEqual(completion["attempt_id"], claim["attempt_id"])

        submitted = transition(
            self.principal_one,
            self.document_id,
            1,
            "SUBMITTED",
            "all locations server-complete",
        )
        self.assertEqual(submitted["revision"], 2)
        with self.assertRaises(InventoryRuleError):
            transition(self.principal_one, self.document_id, 2, "APPROVED", "bypass reconciliation")
        reconciling = transition(
            self.principal_one,
            self.document_id,
            2,
            "RECONCILING",
            "variance review started",
        )
        self.assertEqual(reconciling["revision"], 3)
        with self.assertRaises(InventoryRuleError):
            transition(self.principal_one, self.document_id, 3, "APPROVED", "self approval")
        approved = transition(
            self.principal_two,
            self.document_id,
            3,
            "APPROVED",
            "variance reviewed",
        )
        self.assertEqual(approved["revision"], 4)
        with self.assertRaises(InventoryRuleError):
            transition(self.principal_two, self.document_id, 3, "LOCKED", "stale screen")
        locked = transition(
            self.principal_two,
            self.document_id,
            4,
            "LOCKED",
            "supervisor lock",
        )
        self.assertEqual(locked["revision"], 5)

    def test_load_smoke_preserves_distinct_lease_bound_events(self):
        claim = self.claim()
        signed = [self.signed_event(claim) for _ in range(20)]
        attestation = self.attestation(self.principal_one, self.shift_one)
        started = perf_counter()
        with patch.object(mission_event_module, "attest_shift_at_event", return_value=attestation):
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(
                    executor.map(
                        lambda args: record_event(self.principal_one, *args),
                        signed,
                    )
                )
        elapsed = perf_counter() - started
        self.assertEqual(len({row["event_id"] for row in results}), 20)
        self.assertTrue(all(row["accepted"] for row in results))
        self.assertLess(elapsed, 20, "CI smoke only; this is not production capacity acceptance")


if __name__ == "__main__":
    unittest.main()
