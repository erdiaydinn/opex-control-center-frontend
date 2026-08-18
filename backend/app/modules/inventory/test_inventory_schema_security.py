import unittest

from pydantic import ValidationError

from .schemas import DeviceEnrollCreate, MissionAttemptClaimCreate, TerminalEventCreate


class InventorySchemaSecurityTest(unittest.TestCase):
    def terminal_payload(self) -> dict[str, object]:
        return {
            "event_id": "550e8400-e29b-41d4-a716-446655440001",
            "document_id": "550e8400-e29b-41d4-a716-446655440000",
            "active_shift_id": "SHIFT-1",
            "attempt_id": "550e8400-e29b-41d4-a716-446655440010",
            "lease_id": "550e8400-e29b-41d4-a716-446655440011",
            "device_sequence": 7,
            "location_id": "A01",
            "barcode": "8690000000000",
            "quantity": 2,
            "symbology": "EAN13",
            "occurred_at": "2026-08-15T10:00:00Z",
            "payload_hash": "a" * 64,
        }

    def test_terminal_event_rejects_embedded_tenant_authority(self) -> None:
        for field, value in (
            ("tenant_id", "tenant-b"),
            ("employee_id", "employee-b"),
            ("device_id", "550e8400-e29b-41d4-a716-446655440099"),
            ("warehouse_scope", ["OTHER"]),
        ):
            payload = self.terminal_payload()
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                TerminalEventCreate.model_validate(payload)

    def test_terminal_event_requires_server_issued_attempt_and_lease(self) -> None:
        for field in ("attempt_id", "lease_id", "active_shift_id"):
            payload = self.terminal_payload()
            del payload[field]
            with self.subTest(field=field), self.assertRaises(ValidationError):
                TerminalEventCreate.model_validate(payload)

    def test_terminal_event_accepts_only_canonical_event_fields(self) -> None:
        event = TerminalEventCreate.model_validate(self.terminal_payload())
        self.assertEqual(event.device_sequence, 7)
        self.assertFalse(hasattr(event, "tenant_id"))

    def test_claim_rejects_embedded_identity_authority(self) -> None:
        payload = {
            "document_id": "550e8400-e29b-41d4-a716-446655440000",
            "location_id": "A01",
            "active_shift_id": "SHIFT-1",
            "lease_seconds": 900,
            "payload_hash": "b" * 64,
            "employee_id": "employee-b",
        }
        with self.assertRaises(ValidationError):
            MissionAttemptClaimCreate.model_validate(payload)

    def test_device_enrollment_rejects_embedded_identity_authority(self) -> None:
        payload = {
            "activation_code": "a" * 32,
            "public_key_pem": "-----BEGIN PUBLIC KEY-----\n" + "A" * 120 + "\n-----END PUBLIC KEY-----",
            "tenant_id": "tenant-b",
        }
        with self.assertRaises(ValidationError):
            DeviceEnrollCreate.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
