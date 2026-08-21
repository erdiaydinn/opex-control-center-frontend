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

    def test_recount_link_and_reason_are_device_signature_bound(self):
        base = {
            "active_shift_id": "SHIFT-1",
            "attempt_id": str(uuid4()),
            "barcode": "8690000000001",
            "device_sequence": 2,
            "document_id": str(uuid4()),
            "event_id": str(uuid4()),
            "lease_id": str(uuid4()),
            "location_id": "a01",
            "occurred_at": datetime.now(UTC).isoformat(),
            "quantity": 4,
            "symbology": "EAN13",
            "recount_of_event_id": str(uuid4()),
            "recount_reason_code": "operator_correction",
        }
        canonical = terminal_event_hash_input(base)
        self.assertEqual(canonical["location_id"], "A01")
        self.assertEqual(canonical["recount_reason_code"], "OPERATOR_CORRECTION")
        changed = dict(base, recount_reason_code="SUPERVISOR_REQUEST")
        self.assertNotEqual(
            canonical_payload_hash(canonical),
            canonical_payload_hash(terminal_event_hash_input(changed)),
        )


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
            # v13 intentionally enforces one ACTIVE W2W location per operator.
            # Each unittest method is an independent scenario, so close any
            # ACTIVE attempt left by the preceding scenario without deleting
            # immutable attempt/lease/event history or weakening the DB guard.
            db.execute(
                """UPDATE inventory_mission_attempts
                   SET state='ABANDONED',
                       closed_at=GREATEST(now(), created_at),
                       close_reason='TEST_FIXTURE_ISOLATION'
                   WHERE tenant_id=%s AND state='ACTIVE'""",
                (self.tenant,),
            )
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
        recount_of_event_id=None,
        recount_reason_code=None,
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
        if recount_of_event_id is not None:
            payload["recount_of_event_id"] = str(recount_of_event_id)
            payload["recount_reason_code"] = recount_reason_code
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
        self.assertEqual([item[0] for item in results].count("ok"), 1)
        self.assertEqual([item[0] for item in results].count("blocked"), 1)

    def test_concurrent_duplicate_event_is_exactly_once(self):
        claim = self.claim()
        event_id = uuid4()
        signed = self.signed_event(claim, event_id=event_id)

        def submit():
            try:
                with patch.object(
                    mission_event_module,
                    "attest_shift_at_event",
                    return_value=self.attestation(self.principal_one, self.shift_one),
                ):
                    return record_event(self.principal_one, *signed)
            except InventoryRuleError as error:
                return {"blocked": str(error)}

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: submit(), range(8)))
        event_count = sum(1 for result in results if result.get("event_id") == str(event_id))
        self.assertGreaterEqual(event_count, 1)
        with connect() as db:
            count = db.execute(
                "SELECT count(*) FROM inventory_events WHERE tenant_id=%s AND event_id=%s",
                (self.tenant, event_id),
            ).fetchone()["count"]
        self.assertEqual(count, 1)

    def test_exact_replay_payload_substitution_and_unexpected_sku(self):
        claim = self.claim()
        event_id = uuid4()
        first = self.record_signed_event(claim, event_id=event_id)
        self.assertFalse(first["idempotent"])
        exact = self.record_signed_event(claim, event_id=event_id)
        self.assertTrue(exact["idempotent"])
        with self.assertRaises(InventoryRuleError):
            self.record_signed_event(claim, event_id=event_id, quantity=3)
        unexpected = self.record_signed_event(claim, barcode="8699999999999")
        self.assertEqual(unexpected["status"], "UNEXPECTED_SKU")

    def test_exact_replay_requires_fresh_device_proof(self):
        claim = self.claim()
        event_id = uuid4()
        first = self.record_signed_event(claim, event_id=event_id)
        self.assertFalse(first["idempotent"])
        payload, timestamp, nonce, signature = self.signed_event(claim, event_id=event_id)
        with patch.object(
            mission_event_module,
            "attest_shift_at_event",
            return_value=self.attestation(self.principal_one, self.shift_one),
        ):
            replay = record_event(self.principal_one, payload, timestamp, nonce, signature)
        self.assertTrue(replay["idempotent"])

    def test_duplicate_sku_requires_explicit_versioned_recount(self):
        claim = self.claim()
        first = self.record_signed_event(claim)
        with self.assertRaises(InventoryRuleError):
            self.record_signed_event(claim)
        recount = self.record_signed_event(
            claim,
            recount_of_event_id=first["event_id"],
            recount_reason_code="OPERATOR_CORRECTION",
        )
        self.assertEqual(recount["status"], "COUNTED")

    def test_recount_must_supersede_latest_version(self):
        claim = self.claim()
        first = self.record_signed_event(claim)
        second = self.record_signed_event(
            claim,
            recount_of_event_id=first["event_id"],
            recount_reason_code="OPERATOR_CORRECTION",
        )
        with self.assertRaises(InventoryRuleError):
            self.record_signed_event(
                claim,
                recount_of_event_id=first["event_id"],
                recount_reason_code="OPERATOR_CORRECTION",
            )
        third = self.record_signed_event(
            claim,
            recount_of_event_id=second["event_id"],
            recount_reason_code="SUPERVISOR_REQUEST",
        )
        self.assertEqual(third["status"], "COUNTED")

    def test_exact_replay_is_rejected_after_device_replacement(self):
        claim = self.claim()
        event_id = uuid4()
        first = self.record_signed_event(claim, event_id=event_id)
        self.assertFalse(first["idempotent"])
        with connect() as db:
            db.execute(
                "UPDATE inventory_devices SET status='REPLACED' WHERE tenant_id=%s AND device_id=%s",
                (self.tenant, self.principal_one.device_id),
            )
            db.commit()
        with self.assertRaises(PermissionError):
            self.record_signed_event(claim, event_id=event_id)
        with connect() as db:
            db.execute(
                "UPDATE inventory_devices SET status='ACTIVE' WHERE tenant_id=%s AND device_id=%s",
                (self.tenant, self.principal_one.device_id),
            )
            db.commit()

    def test_valid_offline_event_may_upload_after_lease_expiry(self):
        now = datetime.now(UTC)
        valid_from = now - timedelta(hours=2)
        valid_until = now - timedelta(hours=1)
        claim = self.create_historical_lease(valid_from=valid_from, valid_until=valid_until)
        payload, timestamp, nonce, signature = self.signed_event(
            claim,
            occurred_at=valid_from + timedelta(minutes=30),
        )
        with patch.object(
            mission_event_module,
            "attest_shift_at_event",
            return_value=self.attestation(self.principal_one, self.shift_one),
        ):
            result = record_event(self.principal_one, payload, timestamp, nonce, signature)
        self.assertEqual(result["status"], "COUNTED")

    def test_renewal_cannot_retroactively_authorize_a_past_gap(self):
        now = datetime.now(UTC)
        first_from = now - timedelta(hours=3)
        first_until = now - timedelta(hours=2)
        claim = self.create_historical_lease(valid_from=first_from, valid_until=first_until)
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
                    now - timedelta(minutes=30),
                    now + timedelta(minutes=30),
                ),
            )
            db.commit()
        payload, timestamp, nonce, signature = self.signed_event(
            claim,
            occurred_at=first_until + timedelta(minutes=30),
        )
        with patch.object(
            mission_event_module,
            "attest_shift_at_event",
            return_value=self.attestation(self.principal_one, self.shift_one),
        ):
            with self.assertRaises(InventoryRuleError):
                record_event(self.principal_one, payload, timestamp, nonce, signature)

    def test_superseded_attempt_evidence_is_excluded_from_reconciliation(self):
        old_claim = self.claim()
        self.record_signed_event(old_claim)
        supersede_attempt(
            self.principal_two,
            self.document_id,
            self.location_id,
            UUID(old_claim["attempt_id"]),
            "SUPERVISOR_RECOUNT",
        )
        new_claim = self.claim()
        self.record_signed_event(new_claim, quantity=5)
        self.record_completion(new_claim)
        result = reconciliation(self.principal_two, self.document_id)
        line = next(item for item in result["lines"] if item["sku"] == "SKU-1")
        self.assertEqual(line["counted_quantity"], 5)

    def test_maker_checker_requires_completion_and_reconciliation(self):
        claim = self.claim()
        self.record_signed_event(claim, quantity=10)
        with self.assertRaises(InventoryRuleError):
            transition(self.principal_two, self.document_id, "SUBMITTED", "submit")
        self.record_completion(claim)
        transition(self.principal_two, self.document_id, "SUBMITTED", "submit")
        with self.assertRaises(InventoryRuleError):
            transition(self.principal_two, self.document_id, "APPROVED", "approve")
        reconciliation(self.principal_two, self.document_id)
        transition(self.principal_two, self.document_id, "APPROVED", "approve")
        self.assertEqual(
            transition(self.principal_two, self.document_id, "LOCKED", "lock")["state"],
            "LOCKED",
        )

    def test_load_smoke_preserves_distinct_lease_bound_events(self):
        claim = self.claim()
        started = perf_counter()
        for index in range(50):
            first = self.record_signed_event(
                claim,
                barcode=f"LOAD-{index:04d}",
                quantity=1,
            )
            self.record_signed_event(
                claim,
                recount_of_event_id=first["event_id"],
                recount_reason_code="SUPERVISOR_REQUEST",
                quantity=2,
            )
        elapsed = perf_counter() - started
        with connect() as db:
            count = db.execute(
                """SELECT count(*) FROM inventory_events
                   WHERE tenant_id=%s AND document_id=%s AND attempt_id=%s""",
                (self.tenant, self.document_id, UUID(claim["attempt_id"])),
            ).fetchone()["count"]
        self.assertEqual(count, 100)
        self.assertLess(elapsed, 15.0)
