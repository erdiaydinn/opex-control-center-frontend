from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
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
)
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

        putaway = build_operational_intent(
            "PUTAWAY", {**common, "destination_location_id": "b02"}
        )
        self.assertEqual(putaway["destination_location_id"], "B02")

        receiving = build_operational_intent(
            "RECEIVING", {**common, "container_id": "pallet-9"}
        )
        self.assertIn("DAMAGED", receiving["allowed_conditions"])

        transfer = build_operational_intent(
            "TRANSFER",
            {**common, "source_location_id": "a01", "destination_location_id": "c03"},
        )
        self.assertNotEqual(transfer["source_location_id"], transfer["destination_location_id"])

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
