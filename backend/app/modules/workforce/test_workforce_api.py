"""HTTP-level field-pilot acceptance scenarios for Workforce.

These tests intentionally exercise the same FastAPI/middleware/router boundary
used by the web and native clients. They do not mock the Workforce service.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.modules.workforce import service


ADMIN_HEADERS = {
    "X-OPEX-User": "field-admin@example.com",
    "X-OPEX-Role": "super_admin",
    "X-OPEX-Permissions": "managePeople,importRoster,importTimeOff,createShift,viewWorkforce",
}
PICKER_HEADERS = {"X-OPEX-User": "picker@example.com", "X-OPEX-Role": "picker"}
FULYA = {"latitude": 41.060681, "longitude": 29.006064}


class WorkforceFieldPilotApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=True)

    def setUp(self):
        self.snapshots = {
            "attendance": deepcopy(service._ATTENDANCE),
            "people": deepcopy(service._PEOPLE),
            "leaves": deepcopy(service._LEAVES),
            "breaks": deepcopy(service._BREAK_SESSIONS),
            "tasks": deepcopy(service._CORRECTION_REQUESTS),
            "shifts": deepcopy(service._SHIFTS),
            "challenges": deepcopy(service._DEVICE_CHALLENGES),
            "devices": deepcopy(service._DEVICE_BINDINGS),
            "enrollments": deepcopy(service._ENROLLMENT_TOKENS),
        }
        self.environment = patch.dict(os.environ, {
            "DOCKOS_ENV": "development",
            "OPEX_ALLOW_LEGACY_HEADERS": "true",
            "OPEX_PII_KEY": base64.urlsafe_b64encode(b"field-pilot-key-material-32bytes!"[:32]).decode(),
        }, clear=False)
        self.environment.start()

    def tearDown(self):
        service._ATTENDANCE[:] = self.snapshots["attendance"]
        service._PEOPLE[:] = self.snapshots["people"]
        service._LEAVES[:] = self.snapshots["leaves"]
        service._BREAK_SESSIONS[:] = self.snapshots["breaks"]
        service._CORRECTION_REQUESTS[:] = self.snapshots["tasks"]
        service._SHIFTS[:] = self.snapshots["shifts"]
        service._DEVICE_CHALLENGES.clear(); service._DEVICE_CHALLENGES.update(self.snapshots["challenges"])
        service._DEVICE_BINDINGS[:] = self.snapshots["devices"]
        service._ENROLLMENT_TOKENS.clear(); service._ENROLLMENT_TOKENS.update(self.snapshots["enrollments"])
        self.environment.stop()

    @staticmethod
    def proof(person_id="100184", device_id="DEVICE-1"):
        return {
            "person_id": person_id, **FULYA, "accuracy_meters": 5,
            "device_id": device_id, "device_trusted": True,
            "local_auth_method": "DEVICE_BIOMETRIC",
            "local_auth_at": datetime.now(UTC).isoformat(),
        }

    def test_real_checkin_break_checkout_lifecycle_and_replay_guards(self):
        missing = self.client.post("/api/workforce/shifts/SHIFT-MISSING/check-in", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(missing.status_code, 409)

        check_in = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-in", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(check_in.status_code, 201, check_in.text)
        attendance_id = check_in.json()["id"]
        self.assertNotIn("biometric_image", check_in.json())
        self.assertNotIn("biometric_template", check_in.json())

        duplicate = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-in", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(duplicate.status_code, 409)

        started = self.client.post("/api/workforce/shifts/SHIFT-1407-001/breaks", json={"person_id": "100184", "action": "START"}, headers=PICKER_HEADERS)
        self.assertEqual(started.status_code, 201, started.text)
        blocked = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-out", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("aktif molayı", blocked.text)
        finished = self.client.post("/api/workforce/shifts/SHIFT-1407-001/breaks", json={"person_id": "100184", "action": "FINISH"}, headers=PICKER_HEADERS)
        self.assertEqual(finished.status_code, 201, finished.text)

        check_out = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-out", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(check_out.status_code, 200, check_out.text)
        record = check_out.json()
        self.assertEqual(record["id"], attendance_id)
        self.assertGreaterEqual(record["gross_minutes"], record["net_minutes"])
        self.assertFalse(record.get("continuous_location_stored", False))
        self.assertNotIn("route", record)

        replay = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-out", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(replay.status_code, 409)

    def test_bulk_import_resolves_tc_server_side_and_reports_unknown_rows(self):
        person = {
            "employee_id": "EMP-FIELD-1", "roster_ids": ["RST-FIELD-1"],
            "full_name": "Saha Pilot Personeli", "tckn": "21987654310",
            "position": "Picker", "warehouse_id": "fulya", "active": True,
        }
        created = self.client.post("/api/workforce/people/bulk-upsert", json={"rows": [person]}, headers=ADMIN_HEADERS)
        self.assertEqual(created.status_code, 200, created.text)

        base = {
            "shift_id": "", "person_id": "SOURCE", "name": "Saha Pilot Personeli",
            "role": "Picker", "warehouse": "Fulya", "date": "13.08.2026",
            "planned": "Dosyadan", "check_in": "22:00", "check_out": "06:00",
            "break_minutes": 60, "net_minutes": 1, "expected_minutes": 420,
            "status": "Tamamlandı", "approval": "Onay bekliyor", "source": "Puantaj Dosyası · saha.xlsx",
            "identity_method": "TC",
        }
        rows = [
            {**base, "id": "ATT-FIELD-TC", "source_person_id": "21987654310"},
            {**base, "id": "ATT-FIELD-UNKNOWN", "source_person_id": "99999999999"},
        ]
        imported = self.client.post("/api/workforce/attendance/import", json={"file_name": "saha.xlsx", "rows": rows}, headers=ADMIN_HEADERS)
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["inserted"], 1)
        self.assertEqual(imported.json()["unmatched"], 1)
        record = next(item for item in service._ATTENDANCE if item["id"] == "ATT-FIELD-TC")
        self.assertEqual(record["person_id"], "EMP-FIELD-1")
        self.assertEqual(record["gross_minutes"], 480)
        self.assertEqual(record["net_minutes"], 420)

    def test_production_self_scope_comes_from_verified_sso_employee_claim(self):
        claims = {"sub": "picker-sub", "name": "Pilot Picker", "roles": ["picker"], "permissions": [], "employee_id": "100184"}
        with patch.dict(os.environ, {"DOCKOS_ENV": "production", "OPEX_ALLOW_LEGACY_HEADERS": "false"}, clear=False), patch("app.security._decode_bearer", return_value=claims):
            own = self.client.get("/api/workforce/mobile/bootstrap?person_id=100184", headers={"Authorization": "Bearer signed.jwt"})
            other = self.client.get("/api/workforce/mobile/bootstrap?person_id=100221", headers={"Authorization": "Bearer signed.jwt"})
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual(other.status_code, 403)

    def test_employee_master_bulk_headers_ignore_case_spelling_and_punctuation(self):
        raw = {
            "SİCİL NO": "EMP-HEADER-1",
            "T.C. KİMLİK NUMARASI": "31987654310",
            "PERSONEL ADI": "Başlık Normalizasyonu",
            "DEPO KODU": "fulya",
            "İŞE GİRİŞ TARİHİ": "2026-08-13",
            "ROOSTER ID": "RST-HEADER-1; RST-HEADER-2",
        }
        response = self.client.post("/api/workforce/people/bulk-upsert", json={"rows": [raw]}, headers=ADMIN_HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        person = service.resolve_person_identity("31987654310", "TC")
        self.assertIsNotNone(person)
        self.assertEqual(person["employee_id"], "EMP-HEADER-1")
        self.assertEqual(person["roster_ids"], ["RST-HEADER-1", "RST-HEADER-2"])

    def test_production_manager_scope_filters_reads_and_blocks_cross_warehouse_writes(self):
        claims = {
            "sub": "fulya-manager", "name": "Fulya Saha Yöneticisi",
            "roles": ["warehouse_manager"],
            "permissions": ["viewWorkforce", "viewPeople", "createShift", "viewAuditLog"],
            "warehouse_scope": ["fulya"],
        }
        headers = {"Authorization": "Bearer signed.manager.jwt"}
        cross_warehouse = {
            "person_id": "100287", "person_name": "Kerim Atayolu", "warehouse_id": "uskudar",
            "date": "2026-10-01", "start": "08:00", "end": "17:00", "break_minutes": 60,
            "role": "Picker",
        }
        own_warehouse = {
            "person_id": "100184", "person_name": "Erdi Aydın", "warehouse_id": "fulya",
            "date": "2026-10-01", "start": "08:00", "end": "17:00", "break_minutes": 60,
            "role": "Picker",
        }
        environment = {"DOCKOS_ENV": "production", "OPEX_ALLOW_LEGACY_HEADERS": "false"}
        with patch.dict(os.environ, environment, clear=False), patch("app.security._decode_bearer", return_value=claims):
            bootstrap = self.client.get("/api/workforce/admin/bootstrap", headers=headers)
            shifts = self.client.get("/api/workforce/shifts", headers=headers)
            blocked = self.client.post("/api/workforce/shifts", json=cross_warehouse, headers=headers)
            allowed = self.client.post("/api/workforce/shifts", json=own_warehouse, headers=headers)
            audit = self.client.get("/api/workforce/audit-log", headers=headers)
        self.assertEqual(bootstrap.status_code, 200, bootstrap.text)
        self.assertTrue(bootstrap.json()["warehouses"])
        self.assertTrue(all("fulya" in row["id"].lower() for row in bootstrap.json()["warehouses"]))
        self.assertTrue(all(row.get("warehouse_id") == "fulya" for row in bootstrap.json()["people"]))
        self.assertTrue(all("fulya" in row.get("warehouse", "").lower() for row in bootstrap.json()["attendance"]))
        self.assertTrue(all(row.get("warehouse_id") == "fulya" for row in shifts.json()["rows"]))
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(allowed.status_code, 201, allowed.text)
        self.assertEqual(audit.status_code, 403, audit.text)

        missing_scope = {**claims, "warehouse_scope": []}
        with patch.dict(os.environ, environment, clear=False), patch("app.security._decode_bearer", return_value=missing_scope):
            denied = self.client.get("/api/workforce/admin/bootstrap", headers=headers)
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_gps_accuracy_distance_and_stale_user_presence_fail_closed(self):
        inaccurate = {**self.proof(), "accuracy_meters": 500}
        outside = {**self.proof(), "latitude": 40.0, "longitude": 29.0}
        stale = {**self.proof(), "local_auth_at": "2026-08-13T00:00:00+00:00"}
        for proof, expected in ((inaccurate, "GPS doğruluğu"), (outside, "Depo konumunun dışındasınız"), (stale, "doğrulaması eskimiş")):
            response = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-in", json=proof, headers=PICKER_HEADERS)
            self.assertEqual(response.status_code, 409, response.text)
            self.assertIn(expected, response.text)
        self.assertFalse(any(item.get("shift_id") == "SHIFT-1407-001" for item in service._ATTENDANCE))

    def test_registered_device_reset_attestation_signed_challenge_and_replay(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        reset = self.client.post("/api/workforce/devices/100184/reset", json={"reason": "Pilot cihaz değişimi"}, headers=ADMIN_HEADERS)
        self.assertEqual(reset.status_code, 200, reset.text)
        enrollment_token = reset.json()["enrollment_token"]
        key = ec.generate_private_key(ec.SECP256R1())
        public_key = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        registration = {
            "person_id": "100184", "device_id": "FIELD-DEVICE-NEW", "enrollment_token": enrollment_token,
            "device_key_id": "field-key-100184", "public_key": public_key,
            "attestation_provider": "APPLE_APP_ATTEST", "attestation_token": "field-attestation-token-opaque",
            "model": "iPhone Pilot", "os_version": "iOS 20", "app_version": "28.0", "platform": "IOS",
        }
        with patch("app.modules.workforce.service.verify_attestation", return_value={"valid": True, "environment": "production"}):
            registered = self.client.post("/api/workforce/devices/register", json=registration, headers=PICKER_HEADERS)
            replay_enrollment = self.client.post("/api/workforce/devices/register", json=registration, headers=PICKER_HEADERS)
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertEqual(replay_enrollment.status_code, 409)
        old_device = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-in", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(old_device.status_code, 409)
        self.assertIn("iptal edildi", old_device.text)

        def signed_proof(action):
            challenge = self.client.post("/api/workforce/devices/challenge", json={"person_id": "100184", "device_id": "FIELD-DEVICE-NEW"}, headers=PICKER_HEADERS)
            self.assertEqual(challenge.status_code, 201, challenge.text)
            signature = key.sign(challenge.json()["challenge"].encode(), ec.ECDSA(hashes.SHA256()))
            return {
                **self.proof(device_id="FIELD-DEVICE-NEW"), "device_key_id": "field-key-100184",
                "challenge_id": challenge.json()["id"],
                "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
                "action": action,
            }

        check_in_proof = signed_proof("check-in")
        checked_in = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-in", json=check_in_proof, headers=PICKER_HEADERS)
        replay_challenge = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-in", json=check_in_proof, headers=PICKER_HEADERS)
        self.assertEqual(checked_in.status_code, 201, checked_in.text)
        self.assertEqual(replay_challenge.status_code, 409)
        self.assertIn("daha önce kullanılmış", replay_challenge.text)
        checked_out = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-out", json=signed_proof("check-out"), headers=PICKER_HEADERS)
        self.assertEqual(checked_out.status_code, 200, checked_out.text)

    def test_leave_blocks_shift_public_holiday_is_tagged_and_eleven_hour_actual_is_queued(self):
        people = [
            {"employee_id": "EMP-LEAVE", "roster_ids": [], "full_name": "İzinli Personel", "tckn": "31987654310", "position": "Picker", "warehouse_id": "fulya", "active": True},
            {"employee_id": "EMP-HOLIDAY", "roster_ids": [], "full_name": "Tatil Personeli", "tckn": "41987654310", "position": "Picker", "warehouse_id": "fulya", "active": True},
        ]
        created = self.client.post("/api/workforce/people/bulk-upsert", json={"rows": people}, headers=ADMIN_HEADERS)
        self.assertEqual(created.status_code, 200, created.text)
        leave_rows = [
            {"id": "LEAVE-FIELD", "person_id": "EMP-LEAVE", "person_name": "İzinli Personel", "warehouse": "Fulya", "type_id": "annual", "category": "Yıllık İzin", "date": "2026-09-15", "minutes": 450, "approval": "Onaylandı", "note": "", "source": "Time Off Used", "source_person_id": "EMP-LEAVE", "identity_method": "EMPLOYEE_ID"},
            {"id": "HOLIDAY-FIELD", "person_id": "*", "person_name": "Tüm çalışanlar", "warehouse": "Türkiye", "type_id": "public_holiday", "category": "Saha Resmi Tatili", "date": "2026-09-16", "minutes": 450, "approval": "Onaylandı", "note": "", "source": "Resmi Tatil Takvimi", "source_person_id": "*", "identity_method": "EMPLOYEE_ID"},
        ]
        imported = self.client.post("/api/workforce/leaves/import", json={"file_name": "leave-field.xlsx", "rows": leave_rows}, headers=ADMIN_HEADERS)
        self.assertEqual(imported.status_code, 200, imported.text)
        blocked = self.client.post("/api/workforce/shifts", json={"person_id": "EMP-LEAVE", "person_name": "İzinli Personel", "warehouse_id": "fulya", "date": "2026-09-15", "start": "08:00", "end": "17:00", "break_minutes": 60, "role": "Picker"}, headers=ADMIN_HEADERS)
        self.assertEqual(blocked.status_code, 409)
        holiday = self.client.post("/api/workforce/shifts", json={"person_id": "EMP-HOLIDAY", "person_name": "Tatil Personeli", "warehouse_id": "fulya", "date": "2026-09-16", "start": "08:00", "end": "17:00", "break_minutes": 60, "role": "Picker"}, headers=ADMIN_HEADERS)
        self.assertEqual(holiday.status_code, 201, holiday.text)
        self.assertTrue(holiday.json()["is_public_holiday"])
        self.assertEqual(holiday.json()["public_holiday_name"], "Saha Resmi Tatili")

        checked_in = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-in", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(checked_in.status_code, 201, checked_in.text)
        attendance = next(item for item in service._ATTENDANCE if item["id"] == checked_in.json()["id"])
        attendance["check_in"] = (datetime.now(UTC).replace(microsecond=0) - timedelta(hours=12)).isoformat()
        checked_out = self.client.post("/api/workforce/shifts/SHIFT-1407-001/check-out", json=self.proof(), headers=PICKER_HEADERS)
        self.assertEqual(checked_out.status_code, 200, checked_out.text)
        self.assertTrue(checked_out.json()["daily_max_exception"])
        self.assertEqual(checked_out.json()["status"], "İstisna incelemesi")
        self.assertTrue(any(item.get("attendance_id") == attendance["id"] and item.get("kind") == "DAILY_MAX_EXCEPTION" for item in service._CORRECTION_REQUESTS))

    def test_production_health_exposes_missing_external_pilot_controls(self):
        missing = {
            "DOCKOS_ENV": "production", "OPEX_OIDC_ISSUER": "", "OPEX_OIDC_AUDIENCE": "",
            "OPEX_PII_KEY": "", "APPLE_APP_ATTEST_VERIFY_URL": "", "GOOGLE_PLAY_INTEGRITY_VERIFY_URL": "",
        }
        with patch.dict(os.environ, missing, clear=False):
            response = self.client.get("/api/workforce/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertFalse(response.json()["production_controls"]["continuous_location_tracking"])
        self.assertFalse(response.json()["production_controls"]["biometric_template_storage"])


if __name__ == "__main__":
    unittest.main()
