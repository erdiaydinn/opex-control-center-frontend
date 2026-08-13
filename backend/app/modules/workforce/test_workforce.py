import unittest
import base64
import os
from datetime import UTC, datetime, timedelta

from .authorization import is_action_allowed
from .schemas import LeaveRequestCreateRequest, ManagerTaskResolveRequest
from .service import (
    WorkforceRuleError,
    check_in,
    correct_attendance,
    create_correction_request,
    create_leave_request,
    create_shift,
    get_notification_policy,
    get_feature_flags,
    list_audit,
    list_attendance,
    list_leaves,
    list_people,
    list_warehouses,
    resolve_manager_task,
    resolve_leave_request,
    update_feature_flags,
    update_notification_policy,
    upsert_people,
    import_attendance,
    import_leaves,
    _validate_local_authentication,
)


class WorkforceAuthorizationTests(unittest.TestCase):
    def test_corporate_warehouse_coordinates_are_normalized(self):
        rows = list_warehouses()
        self.assertEqual(len(rows), 127)
        self.assertTrue(all(35 <= row["latitude"] <= 43 for row in rows))
        self.assertTrue(all(25 <= row["longitude"] <= 46 for row in rows))

    def test_tckn_is_encrypted_and_masked_by_server_permission(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"x" * 32).decode()
        try:
            upsert_people([{"employee_id": "PII-TEST", "full_name": "Test Personel", "tckn": "12345678901", "position": "Picker", "active": True}], "hr@opex.local")
            masked = next(row for row in list_people(False) if row["employee_id"] == "PII-TEST")
            full = next(row for row in list_people(True) if row["employee_id"] == "PII-TEST")
            self.assertEqual(masked["tckn"], "12*******01")
            self.assertEqual(full["tckn"], "12345678901")
        finally:
            if previous is None: os.environ.pop("OPEX_PII_KEY", None)
            else: os.environ["OPEX_PII_KEY"] = previous

    def test_people_upsert_uses_tckn_before_changed_employee_number(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"y" * 32).decode()
        try:
            base = {"full_name": "TC Tekil Personel", "tckn": "23456789012", "position": "Picker", "active": True}
            upsert_people([{"employee_id": "OLD-EMP", **base}], "hr@opex.local")
            upsert_people([{"employee_id": "NEW-EMP", **base}], "hr@opex.local")
            matches = [row for row in list_people(True) if row["tckn"] == "23456789012"]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["employee_id"], "OLD-EMP")
            self.assertEqual(matches[0]["source_employee_id"], "NEW-EMP")
        finally:
            if previous is None: os.environ.pop("OPEX_PII_KEY", None)
            else: os.environ["OPEX_PII_KEY"] = previous

    def test_people_upsert_keeps_employee_and_roster_ids_separate(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"z" * 32).decode()
        try:
            base = {"employee_id": "HR-ROSTER-TEST", "full_name": "Roster Kimlik Test", "tckn": "34567890123", "position": "Picker", "active": True}
            first = upsert_people([{**base, "roster_ids": ["R-100"]}], "hr@opex.local")
            second = upsert_people([{**base, "roster_ids": ["R-200"]}], "hr@opex.local")
            person = next(row for row in list_people(True) if row["employee_id"] == "HR-ROSTER-TEST")
            self.assertEqual(first["created"], 1)
            self.assertEqual(second["updated"], 1)
            self.assertEqual(person["employee_id"], "HR-ROSTER-TEST")
            self.assertEqual(person["roster_ids"], ["R-100", "R-200"])
        finally:
            if previous is None: os.environ.pop("OPEX_PII_KEY", None)
            else: os.environ["OPEX_PII_KEY"] = previous

    def test_roster_id_conflict_is_reported_and_not_reassigned(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"q" * 32).decode()
        try:
            first = {"employee_id": "HR-RC-1", "roster_ids": ["R-CONFLICT"], "full_name": "Birinci Personel", "tckn": "45678901234", "position": "Picker", "active": True}
            second = {"employee_id": "HR-RC-2", "roster_ids": ["R-CONFLICT"], "full_name": "İkinci Personel", "tckn": "56789012345", "position": "Picker", "active": True}
            upsert_people([first], "hr@opex.local")
            result = upsert_people([second], "hr@opex.local")
            people = list_people(True)
            self.assertEqual(len(result["roster_conflicts"]), 1)
            self.assertEqual(next(row for row in people if row["employee_id"] == "HR-RC-1")["roster_ids"], ["R-CONFLICT"])
            self.assertEqual(next(row for row in people if row["employee_id"] == "HR-RC-2")["roster_ids"], [])
        finally:
            if previous is None: os.environ.pop("OPEX_PII_KEY", None)
            else: os.environ["OPEX_PII_KEY"] = previous

    def test_attendance_file_updates_file_rows_but_protects_mobile_rows(self):
        file_row = {"id": "ATT-FILE-TEST", "shift_id": "", "person_id": "FILE-PERSON", "name": "Dosya Personeli", "role": "Picker", "warehouse": "Fulya", "date": "01.08.2026", "planned": "Dosyadan", "check_in": None, "check_out": None, "break_minutes": 30, "net_minutes": 450, "expected_minutes": 450, "status": "Tamamlandı", "approval": "Onay bekliyor", "source": "Puantaj Dosyası · test.xlsx", "source_person_id": "77", "identity_method": "TC"}
        first = import_attendance([file_row], "admin", "test.xlsx")
        second = import_attendance([{**file_row, "net_minutes": 465}], "admin", "test.xlsx")
        mobile = next(row for row in list_attendance() if row["id"] == "ATT-1407-002")
        protected = import_attendance([{**file_row, "id": mobile["id"], "person_id": mobile["person_id"], "date": mobile["date"]}], "admin", "test.xlsx")
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["updated"], 1)
        self.assertEqual(protected["protected"], 1)
        self.assertEqual(next(row for row in list_attendance() if row["id"] == "ATT-FILE-TEST")["net_minutes"], 465)

    def test_time_off_import_deduplicates_person_and_day(self):
        row = {"id": "LEAVE-FILE-TEST", "person_id": "LEAVE-PERSON", "person_name": "İzin Personeli", "warehouse": "Fulya", "type_id": "annual", "category": "Yıllık İzin", "date": "2026-08-02", "minutes": 450, "approval": "Onaylandı", "note": "", "source": "Time Off Used", "source_person_id": "88", "identity_method": "TC"}
        first = import_leaves([row], "admin", "izin.xlsx")
        second = import_leaves([{**row, "id": "LEAVE-FILE-TEST-2"}], "admin", "izin.xlsx")
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(len([item for item in list_leaves() if item["person_id"] == "LEAVE-PERSON" and item["date"] == "2026-08-02"]), 1)

    def test_human_explanations_have_no_minimum_character_limit(self):
        manager = ManagerTaskResolveRequest(decision="APPROVED", manager_note="k")
        leave = LeaveRequestCreateRequest(person_id="1", person_name="Erdi Aydın", warehouse="Fulya", leave_type="annual", start_date="2026-07-21", end_date="2026-07-21", note="k")
        self.assertEqual(manager.manager_note, "k")
        self.assertEqual(leave.note, "k")

    def test_manual_correction_is_admin_or_explicit_permission_only(self):
        self.assertTrue(is_action_allowed("super_admin", "", "manualCorrection"))
        self.assertTrue(is_action_allowed("admin", "", "manualCorrection"))
        self.assertTrue(is_action_allowed("viewer", "manualCorrection", "manualCorrection"))
        self.assertFalse(is_action_allowed("viewer", "", "manualCorrection"))
        self.assertFalse(is_action_allowed("viewer", "approveAttendance", "manualCorrection"))

    def test_correction_recalculates_and_keeps_audit(self):
        result = correct_attendance(
            "ATT-1407-003",
            {
                "check_in": "08:10",
                "check_out": "17:10",
                "break_minutes": 60,
                "reason": "Yönetici tarafından doğrulandı",
            },
            "admin@yemeksepeti.com",
        )
        self.assertEqual(result["net_minutes"], 480)
        self.assertEqual(result["missing_minutes"], 0)
        self.assertEqual(result["audit"][-1]["event"], "MANUAL_CORRECTION")

    def test_check_in_requires_assigned_shift(self):
        with self.assertRaisesRegex(WorkforceRuleError, "Atanmış vardiya bulunamadı"):
            check_in(
                "SHIFT-NOT-FOUND",
                {
                    "person_id": "100184",
                    "latitude": 41.0572,
                    "longitude": 28.9973,
                    "accuracy_meters": 10,
                    "device_id": "DEVICE-1",
                    "device_trusted": True,
                },
                "erdi@opex.local",
            )

    def test_check_in_rejects_outside_geofence(self):
        with self.assertRaisesRegex(WorkforceRuleError, "Depo konumunun dışındasınız"):
            check_in(
                "SHIFT-1407-001",
                {
                    "person_id": "100184",
                    "latitude": 40.0000,
                    "longitude": 29.0000,
                    "accuracy_meters": 10,
                    "device_id": "DEVICE-1",
                    "device_trusted": True,
                },
                "erdi@opex.local",
            )

    def test_check_in_rejects_unregistered_device(self):
        with self.assertRaisesRegex(WorkforceRuleError, "personele kayıtlı değil"):
            check_in(
                "SHIFT-1407-001",
                {
                    "person_id": "100184",
                    "latitude": 41.0572,
                    "longitude": 28.9973,
                    "accuracy_meters": 10,
                    "device_id": "COPIED-DEVICE",
                    "device_trusted": True,
                },
                "erdi@opex.local",
            )

    def test_device_local_biometric_assertion_is_fresh_and_stores_no_template(self):
        _validate_local_authentication({
            "local_auth_method": "DEVICE_BIOMETRIC",
            "local_auth_at": datetime.now(UTC).isoformat(),
        })
        with self.assertRaisesRegex(WorkforceRuleError, "doğrulaması eskimiş"):
            _validate_local_authentication({
                "local_auth_method": "DEVICE_BIOMETRIC",
                "local_auth_at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
            })

    def test_global_audit_has_integrity_hash(self):
        correct_attendance(
            "ATT-1407-003",
            {"check_in": "08:10", "check_out": "17:10", "break_minutes": 60, "reason": "Audit hash zinciri testi"},
            "audit@opex.local",
        )
        event = list_audit(1)[0]
        self.assertEqual(event["event"], "MANUAL_CORRECTION")
        self.assertEqual(len(event["hash"]), 64)
        self.assertIn("previous_hash", event)

    def test_shift_applies_automatic_break(self):
        result = create_shift(
            {
                "person_id": "TEST-AUTO-BREAK",
                "person_name": "Test Picker",
                "warehouse_id": "fulya",
                "date": "2026-07-20",
                "start": "08:00",
                "end": "17:00",
                "break_minutes": 0,
                "role": "Picker",
            },
            "manager@opex.local",
        )
        self.assertEqual(result["break_minutes"], 60)
        self.assertEqual(result["expected_minutes"], 480)

    def test_shift_rejects_more_than_eleven_net_hours(self):
        with self.assertRaisesRegex(WorkforceRuleError, "azami 11 saat"):
            create_shift(
                {
                    "person_id": "TEST-MAX-HOURS",
                    "person_name": "Test Picker",
                    "warehouse_id": "fulya",
                    "date": "2026-07-20",
                    "start": "00:00",
                    "end": "13:00",
                    "break_minutes": 60,
                    "role": "Picker",
                },
                "manager@opex.local",
            )

    def test_picker_correction_request_reaches_manager_queue(self):
        request = create_correction_request(
            {
                "person_id": "100184",
                "shift_id": "SHIFT-1407-001",
                "request_type": "Giriş / çıkış düzeltmesi",
                "requested_check_in": "08:05",
                "requested_check_out": "17:05",
                "reason": "Telefon bağlantısı nedeniyle çıkış kaydedilemedi",
            },
            "picker@opex.local",
        )
        self.assertEqual(request["status"], "MANAGER_REVIEW")
        resolved = resolve_manager_task(
            request["id"],
            {"decision": "REJECTED", "manager_note": "Kamera ve vardiya kayıtları doğrulamadı", "requested_check_in": None, "requested_check_out": None, "target_minutes": None},
            "manager@opex.local",
        )
        self.assertEqual(resolved["status"], "REJECTED")

    def test_notification_policy_is_editable_and_audited(self):
        updated = update_notification_policy(
            {"shift_published": True, "check_in_reminder": True, "check_in_reminder_minutes": 20, "check_out_reminder": True, "check_out_reminder_minutes": 10},
            "admin@opex.local",
        )
        self.assertEqual(updated["check_in_reminder_minutes"], 20)
        self.assertEqual(get_notification_policy()["check_out_reminder_minutes"], 10)

    def test_picker_leave_request_is_resolved_by_manager(self):
        request = create_leave_request(
            {"person_id": "100184", "person_name": "Erdi Aydın", "warehouse": "Fulya (İstanbul)", "leave_type": "annual", "start_date": "2026-07-21", "end_date": "2026-07-22", "note": "Aile planı nedeniyle yıllık izin talebi"},
            "picker@opex.local",
        )
        self.assertEqual(request["days"], 2)
        resolved = resolve_leave_request(request["id"], {"decision": "APPROVED", "manager_note": "Vardiya planı uygun, izin onaylandı"}, "manager@opex.local")
        self.assertEqual(resolved["status"], "APPROVED")

    def test_feature_flags_are_admin_configurable(self):
        current = get_feature_flags()
        updated = update_feature_flags({**current, "breaks": False}, "admin@opex.local")
        self.assertFalse(updated["breaks"])
        update_feature_flags({**updated, "breaks": True}, "admin@opex.local")


if __name__ == "__main__":
    unittest.main()
