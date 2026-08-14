import unittest
import base64
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from .authorization import is_action_allowed
from .attestation import AttestationError, verify as verify_attestation
from .schemas import LeaveRequestCreateRequest, ManagerTaskResolveRequest
from .service import (
    WorkforceRuleError,
    check_in,
    check_out,
    correct_attendance,
    create_correction_request,
    create_leave_request,
    create_shift,
    get_notification_policy,
    get_feature_flags,
    list_audit,
    list_attendance,
    list_daily_status,
    list_leaves,
    list_people,
    list_warehouses,
    resolve_manager_task,
    resolve_leave_request,
    update_feature_flags,
    update_notification_policy,
    update_employment_lifecycle,
    upsert_people,
    import_attendance,
    import_leaves,
    issue_device_challenge,
    resolve_person_identity,
    _ATTENDANCE,
    _BREAK_SESSIONS,
    _DEVICE_BINDINGS,
    _DEVICE_CHALLENGES,
    _LEAVES,
    _PEOPLE,
    _SHIFTS,
    _finalize_attendance,
    _initial_snapshot,
    _validate_presence,
    _validate_local_authentication,
)


class WorkforceAuthorizationTests(unittest.TestCase):
    def test_production_cold_start_never_seeds_demo_people_shifts_or_devices(self):
        snapshot = _initial_snapshot(production=True)
        self.assertEqual(snapshot["people"], [])
        self.assertEqual(snapshot["shifts"], [])
        self.assertEqual(snapshot["attendance"], [])
        self.assertEqual(snapshot["devices"], [])
        self.assertEqual(snapshot["device_challenges"], [])
        self.assertGreater(len(snapshot["rules"]), 0)
        self.assertEqual(len(snapshot["warehouses"]), 127)

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

    def test_employee_exit_closes_availability_device_and_challenge_access(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"z" * 32).decode()
        person_id = "EXIT-EMPLOYEE"
        device_id = "EXIT-DEVICE"
        shift_id = "SHIFT-EXIT-FUTURE"
        challenge_id = "CHL-EXIT-PENDING"
        try:
            upsert_people([{
                "employee_id": person_id, "full_name": "Ayrılan Çalışan",
                "tckn": "34567890123", "position": "Picker",
                "warehouse_id": "fulya", "active": True,
            }], "hr@opex.local")
            _DEVICE_BINDINGS.append({
                "person_id": person_id, "device_id": device_id,
                "status": "ACTIVE", "signed_challenge_required": False,
            })
            _DEVICE_CHALLENGES[challenge_id] = {
                "id": challenge_id, "person_id": person_id, "device_id": device_id,
                "used": False, "expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
            }
            _SHIFTS.append({
                "id": shift_id, "person_id": person_id, "person_name": "Ayrılan Çalışan",
                "warehouse_id": "fulya", "date": "2026-12-01", "start": "08:00",
                "end": "17:00", "break_minutes": 60, "role": "Picker", "status": "Atandı",
            })
            result = update_employment_lifecycle([{
                "person_id": person_id, "employment_end": "2026-08-13",
                "identity_method": "EMPLOYEE_ID",
            }], "hr@opex.local", "exit.csv")
            self.assertEqual(result["access_closures"], 1)
            self.assertEqual(result["revoked_devices"], 1)
            self.assertEqual(result["cancelled_shifts"], 1)
            self.assertEqual(result["identity_revocations_queued"], 1)
            self.assertFalse(resolve_person_identity(person_id)["active"])
            self.assertEqual(next(row for row in _DEVICE_BINDINGS if row.get("device_id") == device_id)["status"], "REVOKED")
            self.assertEqual(next(row for row in _SHIFTS if row.get("id") == shift_id)["status"], "İptal")
            self.assertTrue(_DEVICE_CHALLENGES[challenge_id]["used"])
            with self.assertRaisesRegex(WorkforceRuleError, "işten ayrılmış"):
                issue_device_challenge(person_id, device_id, "former.employee")
        finally:
            _PEOPLE[:] = [row for row in _PEOPLE if row.get("employee_id") != person_id]
            _DEVICE_BINDINGS[:] = [row for row in _DEVICE_BINDINGS if row.get("device_id") != device_id]
            _DEVICE_CHALLENGES.pop(challenge_id, None)
            _SHIFTS[:] = [row for row in _SHIFTS if row.get("id") != shift_id]
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

    def test_future_exit_keeps_current_access_and_cancels_only_exit_date_forward(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"f" * 32).decode()
        person_id = "FUTURE-EXIT"
        before_id, after_id = "SHIFT-BEFORE-EXIT", "SHIFT-AFTER-EXIT"
        exit_date = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
        before_date = (datetime.now(UTC).date() + timedelta(days=29)).isoformat()
        try:
            upsert_people([{"employee_id": person_id, "full_name": "Gelecek Çıkış", "tckn": "35467890123", "position": "Picker", "active": True}], "hr")
            _SHIFTS.extend([
                {"id": before_id, "person_id": person_id, "date": before_date, "status": "Atandı"},
                {"id": after_id, "person_id": person_id, "date": exit_date, "status": "Atandı"},
            ])
            result = update_employment_lifecycle([{"person_id": person_id, "employment_end": exit_date, "identity_method": "EMPLOYEE_ID"}], "hr", "future-exit.csv")
            self.assertEqual(result["access_closures"], 0)
            self.assertTrue(resolve_person_identity(person_id)["active"])
            self.assertEqual(next(row for row in _SHIFTS if row["id"] == before_id)["status"], "Atandı")
            self.assertEqual(next(row for row in _SHIFTS if row["id"] == after_id)["status"], "İptal")
        finally:
            _PEOPLE[:] = [row for row in _PEOPLE if row.get("employee_id") != person_id]
            _SHIFTS[:] = [row for row in _SHIFTS if row.get("id") not in {before_id, after_id}]
            if previous is None: os.environ.pop("OPEX_PII_KEY", None)
            else: os.environ["OPEX_PII_KEY"] = previous

    def test_daily_status_keeps_leave_work_and_over_eleven_hour_exception(self):
        attendance = {"id": "ATT-RECON", "person_id": "EMP-RECON", "name": "Mutabakat", "date": "2026-08-03", "net_minutes": 700, "daily_max_minutes": 660, "status": "İstisna"}
        leave = {"id": "LEAVE-RECON", "person_id": "EMP-RECON", "person_name": "Mutabakat", "date": "2026-08-03", "type_id": "annual", "category": "Yıllık İzin", "approval": "Onaylandı"}
        _ATTENDANCE.append(attendance)
        _LEAVES.append(leave)
        try:
            row = next(item for item in list_daily_status() if item["person_id"] == "EMP-RECON")
            self.assertTrue(row["work_present"])
            self.assertTrue(row["leave_present"])
            self.assertTrue(row["leave_work_conflict"])
            self.assertTrue(row["daily_max_exception"])
            self.assertTrue(row["requires_review"])
        finally:
            _ATTENDANCE.remove(attendance)
            _LEAVES.remove(leave)

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
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"i" * 32).decode()
        upsert_people([{"employee_id": "FILE-PERSON", "full_name": "Dosya Personeli", "tckn": "67890123456", "position": "Picker", "active": True}], "hr")
        upsert_people([{"employee_id": "100221", "full_name": "Efe Yılmaz", "tckn": "78901234567", "position": "Picker", "active": True}], "hr")
        file_row = {"id": "ATT-FILE-TEST", "shift_id": "", "person_id": "FILE-PERSON", "name": "Dosya Personeli", "role": "Picker", "warehouse": "Fulya", "date": "01.08.2026", "planned": "Dosyadan", "check_in": None, "check_out": None, "break_minutes": 30, "net_minutes": 450, "expected_minutes": 450, "status": "Tamamlandı", "approval": "Onay bekliyor", "source": "Puantaj Dosyası · test.xlsx", "source_person_id": "FILE-PERSON", "identity_method": "EMPLOYEE_ID"}
        first = import_attendance([file_row], "admin", "test.xlsx")
        second = import_attendance([{**file_row, "net_minutes": 465}], "admin", "test.xlsx")
        mobile = next(row for row in list_attendance() if row["id"] == "ATT-1407-002")
        protected = import_attendance([{**file_row, "id": mobile["id"], "person_id": mobile["person_id"], "source_person_id": mobile["person_id"], "date": mobile["date"]}], "admin", "test.xlsx")
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["updated"], 1)
        self.assertEqual(protected["protected"], 1)
        self.assertEqual(next(row for row in list_attendance() if row["id"] == "ATT-FILE-TEST")["net_minutes"], 465)
        if previous is None: os.environ.pop("OPEX_PII_KEY", None)
        else: os.environ["OPEX_PII_KEY"] = previous

    def test_time_off_import_deduplicates_person_and_day(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"l" * 32).decode()
        upsert_people([{"employee_id": "LEAVE-PERSON", "full_name": "İzin Personeli", "tckn": "89012345678", "position": "Picker", "active": True}], "hr")
        row = {"id": "LEAVE-FILE-TEST", "person_id": "LEAVE-PERSON", "person_name": "İzin Personeli", "warehouse": "Fulya", "type_id": "annual", "category": "Yıllık İzin", "date": "2026-08-02", "minutes": 450, "approval": "Onaylandı", "note": "", "source": "Time Off Used", "source_person_id": "LEAVE-PERSON", "identity_method": "EMPLOYEE_ID"}
        first = import_leaves([row], "admin", "izin.xlsx")
        second = import_leaves([{**row, "id": "LEAVE-FILE-TEST-2"}], "admin", "izin.xlsx")
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(len([item for item in list_leaves() if item["person_id"] == "LEAVE-PERSON" and item["date"] == "2026-08-02"]), 1)
        if previous is None: os.environ.pop("OPEX_PII_KEY", None)
        else: os.environ["OPEX_PII_KEY"] = previous

    def test_server_resolves_tc_to_employee_and_roster_alias(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"r" * 32).decode()
        try:
            upsert_people([{"employee_id": "EMP-RESOLVE", "roster_ids": ["RST-44"], "full_name": "Kimlik Zinciri", "tckn": "90123456789", "position": "Picker", "active": True}], "hr")
            self.assertEqual(resolve_person_identity("90123456789", "TC")["employee_id"], "EMP-RESOLVE")
            self.assertEqual(resolve_person_identity("EMP-RESOLVE", "EMPLOYEE_ID")["roster_ids"], ["RST-44"])
            self.assertEqual(resolve_person_identity("RST-44", "ROSTER_ID")["employee_id"], "EMP-RESOLVE")
        finally:
            if previous is None: os.environ.pop("OPEX_PII_KEY", None)
            else: os.environ["OPEX_PII_KEY"] = previous

    def test_attendance_import_recalculates_overnight_net_and_flags_over_eleven_hours(self):
        previous = os.environ.get("OPEX_PII_KEY")
        os.environ["OPEX_PII_KEY"] = base64.urlsafe_b64encode(b"o" * 32).decode()
        try:
            upsert_people([{"employee_id": "IMPORT-NIGHT", "full_name": "Gece İçe Aktarım", "tckn": "10987654321", "position": "Picker", "active": True}], "hr")
            row = {"id": "ATT-IMPORT-NIGHT", "shift_id": "", "person_id": "IMPORT-NIGHT", "name": "Gece İçe Aktarım", "role": "Picker", "warehouse": "Fulya", "date": "03.08.2026", "planned": "Dosyadan", "check_in": "18:00", "check_out": "06:30", "break_minutes": 30, "net_minutes": 1, "expected_minutes": 450, "status": "Tamamlandı", "approval": "Onay bekliyor", "source": "Puantaj Dosyası · night.xlsx", "source_person_id": "IMPORT-NIGHT", "identity_method": "EMPLOYEE_ID"}
            result = import_attendance([row], "admin", "night.xlsx")
            imported = next(item for item in list_attendance() if item["id"] == row["id"])
            self.assertEqual(imported["gross_minutes"], 750)
            self.assertEqual(imported["net_minutes"], 720)
            self.assertTrue(imported["daily_max_exception"])
            self.assertEqual(result["daily_max_exceptions"], 1)
        finally:
            if previous is None: os.environ.pop("OPEX_PII_KEY", None)
            else: os.environ["OPEX_PII_KEY"] = previous

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

    def test_check_in_rejects_inaccurate_gps_fix(self):
        with self.assertRaisesRegex(WorkforceRuleError, "GPS doğruluğu"):
            check_in("SHIFT-1407-001", {"person_id": "100184", "latitude": 41.060681, "longitude": 29.006064, "accuracy_meters": 500, "device_id": "DEVICE-1", "device_trusted": True}, "picker")

    def test_attestation_adapter_fails_closed_without_vendor_gateway(self):
        with patch.dict(os.environ, {"OPEX_ATTESTATION_MODE": "production", "DOCKOS_ENV": "production"}, clear=True), patch.dict("sys.modules", {"httpx": MagicMock()}):
            with self.assertRaisesRegex(AttestationError, "yapılandırılmamış"):
                verify_attestation("APPLE_APP_ATTEST", "opaque-token", person_id="EMP", device_id="DEV", key_id="KEY")

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

    def test_production_rejects_attendance_without_local_user_presence(self):
        with patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False):
            with self.assertRaisesRegex(WorkforceRuleError, "cihaz üzerinde"):
                _validate_local_authentication({"local_auth_method": "NONE"})

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

    def test_shift_blocks_approved_leave_but_marks_imported_public_holiday(self):
        leave = {"id": "LEAVE-SHIFT-BLOCK", "person_id": "LEAVE-SHIFT-PERSON", "date": "2026-09-01", "type_id": "annual", "category": "Yıllık İzin", "approval": "Onaylandı"}
        holiday = {"id": "HOLIDAY-IMPORTED", "person_id": "*", "date": "2026-09-02", "type_id": "public_holiday", "category": "Pilot Tatil Takvimi", "approval": "Onaylandı"}
        _LEAVES.extend([leave, holiday])
        try:
            with self.assertRaisesRegex(WorkforceRuleError, "onaylı izni"):
                create_shift({"person_id": "LEAVE-SHIFT-PERSON", "person_name": "İzinli Personel", "warehouse_id": "fulya", "date": "2026-09-01", "start": "08:00", "end": "17:00", "break_minutes": 60, "role": "Picker"}, "manager")
            shift = create_shift({"person_id": "HOLIDAY-SHIFT-PERSON", "person_name": "Tatil Vardiyası", "warehouse_id": "fulya", "date": "2026-09-02", "start": "08:00", "end": "17:00", "break_minutes": 60, "role": "Picker"}, "manager")
            self.assertTrue(shift["is_public_holiday"])
            self.assertEqual(shift["public_holiday_name"], "Pilot Tatil Takvimi")
        finally:
            _LEAVES[:] = [item for item in _LEAVES if item.get("id") not in {leave["id"], holiday["id"]}]
            _SHIFTS[:] = [item for item in _SHIFTS if item.get("person_id") != "HOLIDAY-SHIFT-PERSON"]

    def test_overnight_attendance_calculates_total_minus_break_and_night_minutes(self):
        row = {"id": "ATT-NIGHT", "person_id": "NIGHT-PERSON", "date": "2026-08-12", "check_in": "2026-08-12T19:00:00+00:00", "break_minutes": 60, "expected_minutes": 420}
        result = _finalize_attendance(row, datetime.fromisoformat("2026-08-13T03:00:00+00:00"))
        self.assertEqual(result["gross_minutes"], 480)
        self.assertEqual(result["net_minutes"], 420)
        self.assertEqual(result["night_minutes"], 480)
        self.assertFalse(result["daily_max_exception"])

    def test_checkout_calculates_net_and_creates_eleven_hour_exception(self):
        now = datetime.now(UTC)
        shift_id = "SHIFT-FIELD-11H"
        attendance_id = "ATT-FIELD-11H"
        _SHIFTS.append({"id": shift_id, "person_id": "100184", "person_name": "Erdi Aydın", "warehouse_id": "fulya", "date": datetime.now().astimezone().date().isoformat(), "start": "00:00", "end": "23:59", "break_minutes": 0, "role": "Picker", "status": "Vardiyada"})
        _ATTENDANCE.append({"id": attendance_id, "shift_id": shift_id, "person_id": "100184", "name": "Erdi Aydın", "warehouse": "Fulya (İstanbul)", "date": datetime.now().astimezone().date().isoformat(), "planned": "00:00–23:59", "check_in": (now - timedelta(hours=12)).isoformat(), "check_out": None, "break_minutes": 30, "net_minutes": 0, "expected_minutes": 480, "status": "Vardiyada", "approval": "Canlı", "source": "Mobil", "audit": []})
        try:
            result = check_out(shift_id, {"person_id": "100184", "latitude": 41.060681, "longitude": 29.006064, "accuracy_meters": 10, "device_id": "DEVICE-1", "device_trusted": True, "local_auth_method": "NONE", "pilot_simulation": True}, "picker")
            self.assertGreater(result["net_minutes"], 660)
            self.assertTrue(result["daily_max_exception"])
            self.assertEqual(result["status"], "İstisna incelemesi")
        finally:
            _ATTENDANCE[:] = [item for item in _ATTENDANCE if item.get("id") != attendance_id]
            _SHIFTS[:] = [item for item in _SHIFTS if item.get("id") != shift_id]

    def test_signed_device_challenge_is_single_use_and_replay_safe(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        public_key = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        binding = {"person_id": "SIGNED-PERSON", "device_id": "SIGNED-DEVICE", "device_key_id": "signed-key-1", "public_key": public_key, "status": "ACTIVE", "signed_challenge_required": True, "attestation_provider": "APPLE_APP_ATTEST"}
        _DEVICE_BINDINGS.append(binding)
        try:
            challenge = issue_device_challenge("SIGNED-PERSON", "SIGNED-DEVICE", "picker")
            signature = key.sign(challenge["challenge"].encode(), ec.ECDSA(hashes.SHA256()))
            payload = {"person_id": "SIGNED-PERSON", "device_id": "SIGNED-DEVICE", "device_key_id": "signed-key-1", "device_trusted": True, "challenge_id": challenge["id"], "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="), "latitude": 41.060681, "longitude": 29.006064, "accuracy_meters": 10}
            _validate_presence(next(row for row in list_warehouses() if row["name"] == "Fulya (İstanbul)"), payload)
            with self.assertRaisesRegex(WorkforceRuleError, "daha önce kullanılmış"):
                _validate_presence(next(row for row in list_warehouses() if row["name"] == "Fulya (İstanbul)"), payload)
        finally:
            _DEVICE_BINDINGS.remove(binding)

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
