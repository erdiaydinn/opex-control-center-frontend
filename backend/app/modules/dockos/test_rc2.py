import os
import tempfile
import unittest
from datetime import date, timedelta


TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["DOCKOS_STATE_FILE"] = os.path.join(TEMP_DIR.name, "dockos_test_state.json")

from .mock_data import DOCKOS_SETTINGS, MOCK_AUDIT_LOG, MOCK_NOTIFICATION_OUTBOX, MOCK_PURCHASE_ORDERS, MOCK_RESERVATIONS, MOCK_SUPPLIER_ACCESS, MOCK_SUPPLIER_CAPACITY, MOCK_SUPPLIER_DAILY_LIMITS, MOCK_USER_SUPPLIERS
from .schemas import AdminReservationEditRequest, AnalyticsAskRequest, BlockSlotDatesRequest, BulkCapacityRequest, BulkSlotDeleteRequest, BulkSlotEditRequest, CreateReservationRequest, EditSlotCapacityRequest, SlotSelectionItem, SupplierAccessMappingRequest, SupplierAllocationItem, SupplierCapacityBulkRequest, SupplierCapacityMatrixRequest, SupplierDailyLimitRequest
from .service import _ensure_slot_horizon, allowed_suppliers, allowed_warehouses, ask_analytics, block_slot_dates, bulk_delete_slot_capacities, bulk_edit_slot_capacities, bulk_update_capacity, bulk_update_supplier_capacity, bulk_update_supplier_capacity_matrix, cancel_reservation, create_reservation, delete_slot_capacity, delete_supplier_access_mapping, edit_reservation_admin, edit_slot_capacity, get_kpis, get_slot_capacity, process_notifications_system, update_supplier_daily_limit, upsert_supplier_access_mapping


class DockOSRC2Tests(unittest.TestCase):
    def setUp(self):
        MOCK_RESERVATIONS.clear()
        MOCK_SUPPLIER_CAPACITY.clear()
        MOCK_AUDIT_LOG.clear()
        MOCK_NOTIFICATION_OUTBOX.clear()
        MOCK_SUPPLIER_DAILY_LIMITS.clear()
        DOCKOS_SETTINGS["deleted_slots"] = []
        MOCK_SUPPLIER_ACCESS[:] = [{"email": email, "supplier_names": list(suppliers), "warehouse_names": [], "all_warehouses": True, "active": True, "locale": "tr"} for email, suppliers in MOCK_USER_SUPPLIERS.items()]
        for po in MOCK_PURCHASE_ORDERS:
            po["status"] = "OPEN"

    def test_cargo_does_not_require_po_sku_or_shipment_details(self):
        payload = CreateReservationRequest(
            supplier_name="Eti",
            warehouse_name="Ankara DC",
            shipment_mode="KARGO",
            pallet_count=0,
            sku_count=0,
            cargo_date=str(date.today() + timedelta(days=1)),
            cargo_tracking_no="KRG-RC2-001",
        )
        result = create_reservation(payload, "eti@demo.com", "supplier")
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(MOCK_RESERVATIONS[-1]["po_numbers"], [])
        self.assertEqual(MOCK_RESERVATIONS[-1]["shipment_details"], "")
        self.assertEqual(MOCK_NOTIFICATION_OUTBOX[0]["event"], "CREATED")

    def test_supplier_reserved_capacity_is_enforced(self):
        po = next(row for row in MOCK_PURCHASE_ORDERS if row["po_number"] == "PO-ETI-ANK-001")
        slot_date = str(date.today() + timedelta(days=7))
        slot = "08:00 - 09:00"
        allocation = SupplierCapacityBulkRequest(
            warehouse_name="Ankara DC",
            supplier_name="Eti",
            dates=[slot_date],
            slots=[slot],
            reserved_pallet=2,
            reserved_sku=10,
        )
        result = bulk_update_supplier_capacity(allocation, "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(result["status"], "UPDATED")

        first = CreateReservationRequest(
            po_number=po["po_number"], po_numbers=[po["po_number"]],
            supplier_name="Eti", warehouse_name="Ankara DC", shipment_mode="SEVKIYAT",
            pallet_count=2, sku_count=10, slot_date=slot_date, selected_slot=slot,
            shipment_details="RC2 kapasite testi", vehicle_plate="34 RC2 001",
        )
        self.assertEqual(create_reservation(first, "eti@demo.com", "supplier")["status"], "APPROVED")

        po["status"] = "OPEN"
        second = first.model_copy(update={"pallet_count": 1, "sku_count": 1, "vehicle_plate": "34 RC2 002"})
        rejected = create_reservation(second, "eti@demo.com", "supplier")
        self.assertEqual(rejected["status"], "FAILED")
        self.assertIn("kapasitesi yetersiz", rejected["message"])

    def test_multi_supplier_matrix_is_atomic_and_analytics_contract_is_stable(self):
        slot_date = str(date.today() + timedelta(days=3))
        matrix = SupplierCapacityMatrixRequest(
            warehouse_name="Ankara DC",
            dates=[slot_date, str(date.today() + timedelta(days=4))],
            slots=["09:00 - 10:00"],
            allocations=[
                SupplierAllocationItem(supplier_name="Eti", reserved_pallet=10, reserved_sku=100),
                SupplierAllocationItem(supplier_name="Ülker", reserved_pallet=12, reserved_sku=120),
            ],
        )
        result = bulk_update_supplier_capacity_matrix(matrix, "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(result["count"], 4)
        self.assertEqual(len(MOCK_SUPPLIER_CAPACITY), 4)

        MOCK_RESERVATIONS.extend([
            {"reservation_no": "AN-1", "supplier_name": "Eti", "warehouse_name": "Ankara DC", "shipment_mode": "SEVKIYAT", "slot_date": slot_date, "status": "APPROVED", "arrival_check": {"arrived": True, "on_time": False, "dock_compatible": True}},
            {"reservation_no": "AN-2", "supplier_name": "Ülker", "warehouse_name": "Ankara DC", "shipment_mode": "KARGO", "slot_date": slot_date, "status": "COMPLETED", "arrival_check": {"arrived": True, "on_time": True, "dock_compatible": True}},
        ])
        kpis = get_kpis("erdi.aydin@yemeksepeti.com", "admin", date_from=slot_date, date_to=slot_date)
        self.assertEqual(kpis["supplier_breakdown"][0]["name"], "Eti")
        self.assertNotIn("supplier_name", kpis["supplier_breakdown"][0])
        report = ask_analytics(AnalyticsAskRequest(question="Tedarikçi bazında geç geliş raporu ver", filters={"date_from": slot_date, "date_to": slot_date}), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(report["metric"], "late")
        self.assertEqual(report["rows"][0]["name"], "Eti")
        self.assertEqual(report["rows"][0]["value"], 1)

    def test_daily_supplier_limit_and_smart_prompt_preview(self):
        slot_date = str(date.today() + timedelta(days=7))
        update_supplier_daily_limit(SupplierDailyLimitRequest(warehouse_name="Ankara DC", supplier_name="Eti", dates=[slot_date], max_pallet=20), "erdi.aydin@yemeksepeti.com", "admin")
        po = next(row for row in MOCK_PURCHASE_ORDERS if row["po_number"] == "PO-ETI-ANK-001")
        payload = CreateReservationRequest(po_number=po["po_number"], po_numbers=[po["po_number"]], supplier_name="Eti", warehouse_name="Ankara DC", shipment_mode="SEVKIYAT", pallet_count=19, sku_count=20, slot_date=slot_date, selected_slot="10:00 - 11:00", shipment_details="Günlük limit testi", vehicle_plate="34 LIM 019")
        self.assertEqual(create_reservation(payload, "eti@demo.com", "supplier")["status"], "APPROVED")
        self.assertEqual({row["event"] for row in MOCK_NOTIFICATION_OUTBOX}, {"CREATED", "REMINDER_48", "FINAL_24"})
        po["status"] = "OPEN"
        rejected = create_reservation(payload.model_copy(update={"pallet_count": 2, "vehicle_plate": "34 LIM 002"}), "eti@demo.com", "supplier")
        self.assertEqual(rejected["status"], "FAILED")
        self.assertIn("günlük palet limiti", rejected["message"])

        performance = ask_analytics(AnalyticsAskRequest(question="Eti'nin son 1 aylık performansı nasıl", filters={}), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(performance["detected_supplier"], "Eti")
        self.assertTrue(performance["context_notes"])
        preview = ask_analytics(AnalyticsAskRequest(question="Eti için Ankara DC'de bu ay maksimum 20 palet limiti uygula", filters={}), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertTrue(preview["confirmation_required"])
        self.assertEqual(preview["action_preview"]["max_pallet"], 20)

        reservation_no = MOCK_RESERVATIONS[-1]["reservation_no"]
        edited = edit_reservation_admin(reservation_no, AdminReservationEditRequest(slot_date=slot_date, selected_slot="11:00 - 12:00", pallet_count=18, sku_count=20, vehicle_plate="34 EDT 018", vehicle_type="TIR", shipment_details="Merkez depo düzenleme testi", edit_reason="Rampa planı değişti"), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(edited["status"], "UPDATED")
        self.assertIn("EDITED", {row["event"] for row in MOCK_NOTIFICATION_OUTBOX})
        cancelled = cancel_reservation(reservation_no, True, "erdi.aydin@yemeksepeti.com", "admin", "Operasyon planı iptal edildi")
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertIn("CANCELLED", {row["event"] for row in MOCK_NOTIFICATION_OUTBOX})

    def test_conversational_nearest_and_automatic_notification_worker(self):
        next_date = str(date.today() + timedelta(days=6))
        MOCK_RESERVATIONS.append({
            "reservation_no": "DKS-NEXT-001", "supplier_name": "Eti", "warehouse_name": "Ankara DC",
            "shipment_mode": "SEVKIYAT", "slot_date": next_date, "selected_slot": "12:00 - 13:00",
            "status": "APPROVED", "pallet_count": 8, "sku_count": 40, "vehicle_plate": "34 NEXT 01",
        })
        answer = ask_analytics(AnalyticsAskRequest(
            question="Sen en yakın rezervasyon hangi tedarikçiye ait",
            filters={"date_from": str(date.today() - timedelta(days=30)), "date_to": str(date.today()), "locale": "de"},
        ), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(answer["visualization"], "answer")
        self.assertEqual(answer["answer_cards"][0]["value"], "Eti")
        self.assertEqual(answer["title"], "Nächste Reservierung")

        MOCK_NOTIFICATION_OUTBOX.append({
            "key": "auto-test", "reservation_no": "DKS-NEXT-001", "event": "CREATED",
            "due_at": str(date.today()) + "T00:00:00", "recipients": ["eti@demo.com"],
            "subject": "Test", "html": "<b>Test</b>", "status": "PENDING", "attempts": 0,
        })
        old_host = os.environ.pop("DOCKOS_SMTP_HOST", None)
        old_backup = os.environ.get("DOCKOS_BACKUP_DIR")
        backup_dir = os.path.join(TEMP_DIR.name, "backups")
        os.environ["DOCKOS_BACKUP_DIR"] = backup_dir
        try:
            result = process_notifications_system()
            self.assertEqual(result["waiting_config"], 1)
            self.assertEqual(MOCK_NOTIFICATION_OUTBOX[-1]["status"], "WAITING_CONFIG")
            self.assertTrue(any(name.startswith("dockos_state_") for name in os.listdir(backup_dir)))
        finally:
            if old_host is not None:
                os.environ["DOCKOS_SMTP_HOST"] = old_host
            if old_backup is None:
                os.environ.pop("DOCKOS_BACKUP_DIR", None)
            else:
                os.environ["DOCKOS_BACKUP_DIR"] = old_backup

    def test_supplier_email_mapping_enforces_supplier_and_warehouse_access(self):
        email = "buyer.access@example.org"
        result = upsert_supplier_access_mapping(SupplierAccessMappingRequest(
            email=email, supplier_names=["Eti"], warehouse_names=["Ankara DC"],
            all_warehouses=False, active=True, locale="en",
        ), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(result["status"], "UPDATED")
        self.assertEqual(allowed_suppliers(email, "supplier"), ["Eti"])
        self.assertEqual(allowed_warehouses(email, "supplier"), ["Ankara DC"])

        po = next(row for row in MOCK_PURCHASE_ORDERS if row["po_number"] == "PO-ETI-EUR-002")
        payload = CreateReservationRequest(
            po_number=po["po_number"], po_numbers=[po["po_number"]], supplier_name="Eti",
            warehouse_name="İstanbul Avrupa DC", shipment_mode="SEVKIYAT", pallet_count=1,
            sku_count=1, slot_date=str(date.today() + timedelta(days=8)), selected_slot="08:00 - 09:00",
            shipment_details="Yetki sınırı testi", vehicle_plate="34 ACL 001",
        )
        with self.assertRaises(PermissionError):
            create_reservation(payload, email, "supplier")
        self.assertEqual(delete_supplier_access_mapping(email, "erdi.aydin@yemeksepeti.com", "admin")["status"], "DELETED")
        self.assertEqual(allowed_suppliers(email, "supplier"), [])

    def test_evening_and_cross_midnight_slots_can_be_added_later(self):
        slot_date = str(date.today() + timedelta(days=15))
        result = bulk_update_capacity(BulkCapacityRequest(
            warehouse_name="Ankara DC",
            dates=[slot_date],
            slots=["23:30 - 00:30", "00:30 - 01:30"],
            max_pallet=25,
            max_sku=250,
        ), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(result["count"], 2)
        rows = get_slot_capacity("Ankara DC", slot_date)
        custom = {row["slot"]: row for row in rows if row["slot"] in {"23:30 - 00:30", "00:30 - 01:30"}}
        self.assertEqual(set(custom), {"23:30 - 00:30", "00:30 - 01:30"})
        self.assertTrue(all(row["max_pallet"] == 25 for row in custom.values()))

    def test_dates_can_be_blocked_then_slots_edited_and_permanently_deleted(self):
        slot_date = str(date.today() + timedelta(days=20))
        blocked = block_slot_dates(BlockSlotDatesRequest(warehouse_name="Ankara DC", dates=[slot_date]), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertTrue(all(row["max_pallet"] == 0 and row["max_sku"] == 0 for row in get_slot_capacity("Ankara DC", slot_date)))

        bulk_update_capacity(BulkCapacityRequest(warehouse_name="Ankara DC", dates=[slot_date], slots=["19:30 - 20:30"], max_pallet=30, max_sku=300), "erdi.aydin@yemeksepeti.com", "admin")
        edited = edit_slot_capacity(EditSlotCapacityRequest(warehouse_name="Ankara DC", date=slot_date, current_slot="19:30 - 20:30", new_slot="19:45 - 20:45", max_pallet=35, max_sku=350), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(edited["row"]["slot"], "19:45 - 20:45")
        self.assertEqual(edited["row"]["max_pallet"], 35)

        deleted = delete_slot_capacity("Ankara DC", slot_date, "19:45 - 20:45", "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(deleted["status"], "DELETED")
        _ensure_slot_horizon()
        self.assertNotIn("19:45 - 20:45", {row["slot"] for row in get_slot_capacity("Ankara DC", slot_date)})

    def test_selected_slots_can_be_bulk_edited_and_partially_deleted(self):
        slot_date = str(date.today() + timedelta(days=30))
        slots = ["01:00 - 02:00", "02:00 - 03:00"]
        bulk_update_capacity(BulkCapacityRequest(
            warehouse_name="Ankara DC", dates=[slot_date], slots=slots,
            max_pallet=20, max_sku=200,
        ), "erdi.aydin@yemeksepeti.com", "admin")

        selected = [SlotSelectionItem(date=slot_date, slot=slot) for slot in slots]
        edited = bulk_edit_slot_capacities(BulkSlotEditRequest(
            warehouse_name="Ankara DC", items=selected, max_pallet=45, max_sku=450,
        ), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(edited["count"], 2)
        updated = {row["slot"]: row for row in get_slot_capacity("Ankara DC", slot_date)}
        self.assertTrue(all(updated[slot]["max_pallet"] == 45 for slot in slots))

        deleted = bulk_delete_slot_capacities(BulkSlotDeleteRequest(
            warehouse_name="Ankara DC", items=[selected[0]],
        ), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertEqual(deleted["count"], 1)
        remaining = {row["slot"] for row in get_slot_capacity("Ankara DC", slot_date)}
        self.assertNotIn(slots[0], remaining)
        self.assertIn(slots[1], remaining)

    def test_long_block_replaces_overlapping_hourly_slots_for_supplier_booking(self):
        slot_date = str(date.today() + timedelta(days=25))
        result = bulk_update_capacity(BulkCapacityRequest(
            warehouse_name="Ankara DC", dates=[slot_date], slots=["10:00 - 14:00"],
            max_pallet=40, max_sku=500,
        ), "erdi.aydin@yemeksepeti.com", "admin")
        self.assertGreaterEqual(result["removed_overlaps"], 4)
        visible = {row["slot"] for row in get_slot_capacity("Ankara DC", slot_date)}
        self.assertIn("10:00 - 14:00", visible)
        self.assertTrue({"10:00 - 11:00", "11:00 - 12:00", "12:00 - 13:00", "13:00 - 14:00"}.isdisjoint(visible))

        MOCK_RESERVATIONS.append({
            "reservation_no": "DKS-OVERLAP-001", "supplier_name": "Eti", "warehouse_name": "Ankara DC",
            "shipment_mode": "SEVKIYAT", "slot_date": slot_date, "selected_slot": "14:00 - 15:00",
            "status": "APPROVED", "pallet_count": 1, "sku_count": 1,
        })
        with self.assertRaisesRegex(ValueError, "çakışan aktif rezervasyon"):
            bulk_update_capacity(BulkCapacityRequest(
                warehouse_name="Ankara DC", dates=[slot_date], slots=["13:30 - 15:30"],
                max_pallet=40, max_sku=500,
            ), "erdi.aydin@yemeksepeti.com", "admin")


if __name__ == "__main__":
    unittest.main()
