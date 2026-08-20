from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from .operational_mission import (
    DEFINITIONS,
    build_operational_intent,
    claim_operational_mission,
    event_hash_input,
    normalize_operational_value,
    operational_value_hash,
    record_operational_event,
)
from .operational_mobile import _project_operational_mobile_row
from .operational_mobile_router import _operational_event_response
from .production import InventoryPrincipal, canonical_payload_hash, connect
from .service import InventoryRuleError


class OperationalMissionContractTests(unittest.TestCase):
    def test_all_workflows_end_once_with_complete(self):
        for _kind, (_operation, steps) in DEFINITIONS.items():
            self.assertEqual(steps[-1], "COMPLETE")
            self.assertEqual(steps.count("COMPLETE"), 1)

    def test_authority_fields_are_hash_bound(self):
        payload = {
            "event_id": str(uuid4()),
            "mission_id": str(uuid4()),
            "claim_id": str(uuid4()),
            "active_shift_id": "SHIFT-1",
            "device_sequence": 9,
            "step_kind": "ITEM",
            "value_hash": "a" * 64,
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        first = canonical_payload_hash(event_hash_input(payload))
        changed = dict(payload, active_shift_id="SHIFT-2")
        self.assertNotEqual(first, canonical_payload_hash(event_hash_input(changed)))

    def test_typed_value_hash_normalizes_quantity_and_codes(self):
        self.assertEqual(normalize_operational_value("QUANTITY", "12.000"), "12")
        self.assertEqual(normalize_operational_value("SOURCE_LOCATION", " a-04-02 "), "A-04-02")
        self.assertEqual(normalize_operational_value("CONDITION", "good"), "GOOD")
        self.assertEqual(len(operational_value_hash("ITEM", "8690000000001")), 64)
        self.assertNotEqual(
            operational_value_hash("ITEM", "8690000000001"),
            operational_value_hash("ITEM", "8690000000002"),
        )

    def test_all_four_mission_intents_are_real_and_type_scoped(self):
        common = {
            "sku_id": "SKU-1",
            "item_barcode": "8690000000001",
            "planned_quantity": Decimal("4"),
            "allowed_conditions": ["GOOD", "DAMAGED"],
        }
        picking = build_operational_intent(
            "PICKING", {**common, "source_location_id": "a01", "container_id": "tote-1"}
        )
        self.assertEqual(picking["source_location_id"], "A01")
        self.assertEqual(picking["container_id"], "TOTE-1")
        self.assertEqual(picking["allowed_conditions"], [])

        putaway = build_operational_intent(
            "PUTAWAY", {**common, "destination_location_id": "b02"}
        )
        self.assertEqual(putaway["destination_location_id"], "B02")
        self.assertEqual(putaway["allowed_conditions"], [])

        receiving = build_operational_intent(
            "RECEIVING", {**common, "container_id": "pallet-9"}
        )
        self.assertIn("DAMAGED", receiving["allowed_conditions"])

        transfer = build_operational_intent(
            "TRANSFER",
            {**common, "source_location_id": "a01", "destination_location_id": "c03"},
        )
        self.assertNotEqual(transfer["source_location_id"], transfer["destination_location_id"])
        self.assertEqual(transfer["allowed_conditions"], [])

    def test_receiving_intent_requires_explicit_condition_authority(self):
        with self.assertRaises(InventoryRuleError):
            build_operational_intent(
                "RECEIVING",
                {
                    "sku_id": "SKU-1",
                    "item_barcode": "8690000000001",
                    "planned_quantity": 1,
                    "container_id": "PALLET-1",
                    "allowed_conditions": [],
                },
            )

    def test_transfer_same_source_and_destination_fails_closed(self):
        with self.assertRaises(InventoryRuleError):
            build_operational_intent(
                "TRANSFER",
                {
                    "sku_id": "SKU-1",
                    "item_barcode": "8690000000001",
                    "planned_quantity": 1,
                    "source_location_id": "A01",
                    "destination_location_id": "A01",
                },
            )

    def test_mobile_projection_is_safe_resumable_and_step_accurate(self):
        principal = InventoryPrincipal(
            "tenant-a",
            "sub-a",
            "EMP-A",
            frozenset({"WH-1"}),
            uuid4(),
        )
        row = {
            "mission_id": uuid4(),
            "warehouse_id": "WH-1",
            "mission_type": "PICKING",
            "operation": "inventory.pick.capture",
            "external_reference": "ORDER-42",
            "steps": ["SOURCE_LOCATION", "ITEM", "QUANTITY", "CONTAINER", "COMPLETE"],
            "state": "CLAIMED",
            "sku_id": "SKU-1",
            "planned_quantity": Decimal("4.000"),
            "source_location_id": "A01",
            "destination_location_id": None,
            "container_id": "TOTE-1",
            "allowed_conditions": ["GOOD"],
            "claim_employee_id": "EMP-A",
            "claim_device_id": principal.device_id,
            "claim_shift_id": "SHIFT-A",
            "completed_steps": 2,
        }
        projected = _project_operational_mobile_row(row, principal, "SHIFT-A")
        self.assertIsNotNone(projected)
        self.assertEqual(projected["claim_status"], "RESUMABLE")
        self.assertEqual(projected["next_step"], "QUANTITY")
        self.assertEqual(projected["planned_quantity"], "4")
        self.assertEqual(projected["allowed_conditions"], [])
        self.assertNotIn("item_value_hash", projected)
        self.assertNotIn("claim_id", projected)

        foreign = dict(row, claim_employee_id="EMP-B")
        self.assertIsNone(_project_operational_mobile_row(foreign, principal, "SHIFT-A"))
        stale_shift = dict(row, claim_shift_id="SHIFT-OLD")
        self.assertIsNone(_project_operational_mobile_row(stale_shift, principal, "SHIFT-A"))

    def test_receiving_projection_requires_server_frozen_condition_authority(self):
        principal = InventoryPrincipal(
            "tenant-a",
            "sub-a",
            "EMP-A",
            frozenset({"WH-1"}),
            uuid4(),
        )
        row = {
            "mission_id": uuid4(),
            "warehouse_id": "WH-1",
            "mission_type": "RECEIVING",
            "operation": "inventory.receiving.capture",
            "external_reference": "ASN-42",
            "steps": ["CONTAINER", "ITEM", "QUANTITY", "CONDITION", "COMPLETE"],
            "state": "OPEN",
            "sku_id": "SKU-1",
            "planned_quantity": Decimal("4"),
            "source_location_id": None,
            "destination_location_id": None,
            "container_id": "PALLET-1",
            "allowed_conditions": [],
            "claim_employee_id": None,
            "claim_device_id": None,
            "claim_shift_id": None,
            "completed_steps": 0,
        }
        self.assertIsNone(_project_operational_mobile_row(row, principal, "SHIFT-A"))
        projected = _project_operational_mobile_row(
            {**row, "allowed_conditions": ["GOOD", "DAMAGED"]},
            principal,
            "SHIFT-A",
        )
        self.assertEqual(projected["allowed_conditions"], ["GOOD", "DAMAGED"])

    def test_mobile_ack_preserves_authoritative_exact_replay_semantics(self):
        first = _operational_event_response(
            {"code": "ACCEPTED", "mission_id": str(uuid4()), "idempotent_replay": False},
            "SHIFT-A",
            str(uuid4()),
        )
        replay = _operational_event_response(
            {"code": "ACCEPTED", "mission_id": str(uuid4()), "idempotent_replay": True},
            "SHIFT-A",
            str(uuid4()),
        )
        self.assertTrue(first["accepted"])
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["accepted"])
        self.assertTrue(replay["idempotent_replay"])

    @patch("backend.app.modules.inventory.operational_mission._assert_active_device")
    def test_foreign_live_claim_is_rejected(self, active_device):
        if not os.getenv("INVENTORY_DATABASE_URL"):
            self.skipTest("requires PostgreSQL")
        tenant = os.getenv("INVENTORY_TEST_TENANT", "eay-inventory-ci")
        mission_id = uuid4()
        device_a, device_b = uuid4(), uuid4()
        principal_a = InventoryPrincipal(tenant, "sub-a", "EMP-A", frozenset({"WH-1"}), device_a)
        principal_b = InventoryPrincipal(tenant, "sub-b", "EMP-B", frozenset({"WH-1"}), device_b)
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_devices(
                     tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                   ) VALUES(%s,%s,'EMP-A','TEST-KEY',%s,'ACTIVE'),
                           (%s,%s,'EMP-B','TEST-KEY',%s,'ACTIVE')""",
                (tenant, device_a, f"test-mdm-{device_a}", tenant, device_b, f"test-mdm-{device_b}"),
            )
            db.execute(
                """INSERT INTO inventory_operational_missions(
                   tenant_id,mission_id,warehouse_id,mission_type,operation,external_reference,steps,created_by,
                   intent_version,sku_id,item_value_hash,planned_quantity,source_location_id,container_id,allowed_conditions
                   ) VALUES(%s,%s,'WH-1','PICKING','inventory.pick.capture','ORDER-1',%s::jsonb,'sub-a',
                            1,'SKU-1',%s,1,'A01','TOTE-1','[\"GOOD\"]'::jsonb)""",
                (tenant, mission_id, '["SOURCE_LOCATION","ITEM","QUANTITY","CONTAINER","COMPLETE"]', "a" * 64),
            )
            db.commit()
        first = claim_operational_mission(principal_a, mission_id, "SHIFT-A")
        self.assertEqual(first["next_step"], "SOURCE_LOCATION")
        with self.assertRaises(InventoryRuleError):
            claim_operational_mission(principal_b, mission_id, "SHIFT-B")


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class OperationalMissionPostgresTests(unittest.TestCase):
    def test_v8_columns_guards_and_business_contract_exist(self):
        with connect() as db:
            tables = db.execute(
                """SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class
                   WHERE relname IN (
                     'inventory_operational_missions','inventory_operational_claims',
                     'inventory_operational_events','inventory_operational_event_responses'
                   ) ORDER BY relname"""
            ).fetchall()
            self.assertEqual(len(tables), 4)
            self.assertTrue(all(row["relrowsecurity"] and row["relforcerowsecurity"] for row in tables))
            triggers = db.execute(
                """SELECT tgname FROM pg_trigger
                   WHERE tgname IN (
                     'inventory_operational_events_immutable',
                     'inventory_operational_intent_v8_guard',
                     'inventory_operational_event_v8_guard'
                   ) AND NOT tgisinternal"""
            ).fetchall()
            self.assertEqual(
                {row["tgname"] for row in triggers},
                {
                    "inventory_operational_events_immutable",
                    "inventory_operational_intent_v8_guard",
                    "inventory_operational_event_v8_guard",
                },
            )
            columns = db.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_name='inventory_operational_missions'
                     AND column_name IN (
                       'intent_version','sku_id','item_value_hash','planned_quantity',
                       'actual_quantity','reconciliation_state','result_hash'
                     )"""
            ).fetchall()
            self.assertEqual(len(columns), 7)
            event_columns = db.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_name='inventory_operational_events'
                     AND column_name IN ('contract_version','safe_value','numeric_value')"""
            ).fetchall()
            self.assertEqual(len(event_columns), 3)
            v9 = db.execute(
                "SELECT name FROM inventory_schema_migrations WHERE version=9"
            ).fetchone()
            self.assertIsNotNone(v9)
            default = db.execute(
                """SELECT column_default FROM information_schema.columns
                   WHERE table_name='inventory_operational_missions'
                     AND column_name='allowed_conditions'"""
            ).fetchone()["column_default"]
            self.assertIn("[]", default)

    @patch("backend.app.modules.inventory.operational_mission._verify_device_proof")
    def test_exact_replay_is_bound_to_original_actor_device_shift_and_scope(self, proof):
        tenant = os.getenv("INVENTORY_TEST_TENANT", "eay-inventory-ci")
        mission_id = uuid4()
        claim_id = uuid4()
        event_id = uuid4()
        device_a = uuid4()
        device_b = uuid4()
        principal_a = InventoryPrincipal(tenant, "sub-a", "EMP-REPLAY-A", frozenset({"WH-1"}), device_a)
        principal_b = InventoryPrincipal(tenant, "sub-b", "EMP-REPLAY-B", frozenset({"WH-1"}), device_b)
        occurred_at = datetime.now(UTC).isoformat()
        value_hash = operational_value_hash("SOURCE_LOCATION", "A01")
        payload = {
            "event_id": str(event_id),
            "mission_id": str(mission_id),
            "claim_id": str(claim_id),
            "active_shift_id": "SHIFT-A",
            "device_sequence": 1,
            "step_kind": "SOURCE_LOCATION",
            "value": "A01",
            "value_hash": value_hash,
            "occurred_at": occurred_at,
        }
        payload["payload_hash"] = canonical_payload_hash(event_hash_input(payload))
        stored = {
            "event_id": str(event_id),
            "code": "ACCEPTED",
            "mission_id": str(mission_id),
            "completed": False,
            "next_step": "ITEM",
            "idempotent_replay": False,
        }
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_devices(
                     tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                   ) VALUES(%s,%s,'EMP-REPLAY-A','TEST-KEY',%s,'ACTIVE')""",
                (tenant, device_a, f"test-mdm-{device_a}"),
            )
            db.execute(
                """INSERT INTO inventory_operational_missions(
                   tenant_id,mission_id,warehouse_id,mission_type,operation,external_reference,steps,created_by,
                   state,intent_version,sku_id,item_value_hash,planned_quantity,source_location_id,container_id,allowed_conditions
                   ) VALUES(%s,%s,'WH-1','PICKING','inventory.pick.capture',%s,%s::jsonb,'sub-a',
                            'CLAIMED',1,'SKU-1',%s,1,'A01','TOTE-1','[]'::jsonb)""",
                (
                    tenant,
                    mission_id,
                    f"ORDER-{mission_id}",
                    '["SOURCE_LOCATION","ITEM","QUANTITY","CONTAINER","COMPLETE"]',
                    operational_value_hash("ITEM", "8690000000001"),
                ),
            )
            db.execute(
                """INSERT INTO inventory_operational_claims(
                   tenant_id,claim_id,mission_id,employee_id,device_id,shift_id
                   ) VALUES(%s,%s,%s,'EMP-REPLAY-A',%s,'SHIFT-A')""",
                (tenant, claim_id, mission_id, device_a),
            )
            db.execute(
                """INSERT INTO inventory_operational_events(
                   tenant_id,event_id,mission_id,claim_id,employee_id,device_id,shift_id,
                   device_sequence,step_index,step_kind,value_hash,payload_hash,occurred_at,
                   contract_version,safe_value,numeric_value
                   ) VALUES(%s,%s,%s,%s,'EMP-REPLAY-A',%s,'SHIFT-A',1,0,'SOURCE_LOCATION',%s,%s,%s,1,'A01',NULL)""",
                (tenant, event_id, mission_id, claim_id, device_a, value_hash, payload["payload_hash"], occurred_at),
            )
            db.execute(
                """INSERT INTO inventory_operational_event_responses(tenant_id,event_id,response)
                   VALUES(%s,%s,%s::jsonb)""",
                (tenant, event_id, json.dumps(stored, sort_keys=True)),
            )
            db.commit()

        replay = record_operational_event(principal_a, payload, occurred_at, "nonce-a", "signature-a")
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["event_id"], str(event_id))
        with self.assertRaises(PermissionError):
            record_operational_event(principal_b, payload, occurred_at, "nonce-b", "signature-b")
