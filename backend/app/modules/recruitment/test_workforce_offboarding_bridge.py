from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import patch

from app.modules.recruitment import workforce_offboarding_bridge as bridge


class WorkforceOffboardingBridgeTests(unittest.TestCase):
    def person(self, *, active=True, employment_end=None):
        return {"employee_id": "EMP-1", "active": active, "employment_end": employment_end}

    def test_missing_employee_fails_closed(self):
        with patch.object(bridge.workforce_service, "resolve_person_identity", return_value=None):
            with self.assertRaisesRegex(bridge.WorkforceOffboardingBridgeError, "Employee Master"):
                bridge.apply_offboarding_to_workforce(
                    "EMP-404", effective_at=datetime.now(UTC), actor="hr"
                )

    def test_conflicting_employment_end_is_not_overwritten(self):
        effective = datetime.now(UTC)
        with patch.object(
            bridge.workforce_service,
            "resolve_person_identity",
            return_value=self.person(active=True, employment_end="2099-01-01"),
        ), patch.object(bridge.workforce_service, "list_shifts", return_value=[]), patch.object(
            bridge.workforce_service, "update_employment_lifecycle"
        ) as update:
            with self.assertRaisesRegex(bridge.WorkforceOffboardingBridgeError, "reconciliation"):
                bridge.apply_offboarding_to_workforce("EMP-1", effective_at=effective, actor="hr")
        update.assert_not_called()

    def test_same_authoritative_end_is_idempotent(self):
        future = datetime.now(UTC) + timedelta(days=3)
        expected = future.astimezone(bridge._ISTANBUL).date().isoformat()
        person = self.person(active=True, employment_end=expected)
        with patch.object(bridge.workforce_service, "resolve_person_identity", return_value=person), patch.object(
            bridge.workforce_service, "list_shifts", return_value=[]
        ), patch.object(bridge.workforce_service, "update_employment_lifecycle") as update, patch.object(
            bridge.workforce_service, "person_has_workforce_access", return_value=True
        ):
            result = bridge.apply_offboarding_to_workforce("EMP-1", effective_at=future, actor="hr")
        self.assertTrue(result["idempotent_replay"])
        self.assertEqual(result["access_state"], "SCHEDULED")
        update.assert_not_called()

    def test_effective_exit_requires_inactive_master_and_no_future_shift(self):
        effective = datetime.now(UTC)
        end = effective.astimezone(bridge._ISTANBUL).date().isoformat()
        before = self.person(active=True, employment_end=None)
        after = self.person(active=False, employment_end=end)
        with patch.object(bridge.workforce_service, "resolve_person_identity", side_effect=[before, after]), patch.object(
            bridge.workforce_service, "list_shifts", side_effect=[
                [{"id": "S1", "date": end, "status": "Atandı"}],
                [],
            ]
        ), patch.object(
            bridge.workforce_service,
            "update_employment_lifecycle",
            return_value={"matched": 1, "unmatched": 0, "access_closures": 1, "revoked_devices": 1, "cancelled_shifts": 1, "identity_revocations_queued": 1},
        ) as update, patch.object(bridge.workforce_service, "person_has_workforce_access", return_value=False):
            result = bridge.apply_offboarding_to_workforce("EMP-1", effective_at=effective, actor="hr")
        self.assertEqual(result["access_state"], "DEACTIVATED")
        self.assertFalse(result["workforce_access_allowed"])
        self.assertEqual(result["cancelled_shifts"], 1)
        self.assertEqual(result["identity_revocations_queued"], 1)
        self.assertFalse(result["idempotent_replay"])
        update.assert_called_once()

    def test_active_future_shift_after_projection_blocks_close(self):
        future = datetime.now(UTC) + timedelta(days=3)
        end = future.astimezone(bridge._ISTANBUL).date().isoformat()
        before = self.person(active=True, employment_end=None)
        after = self.person(active=True, employment_end=end)
        with patch.object(bridge.workforce_service, "resolve_person_identity", side_effect=[before, after]), patch.object(
            bridge.workforce_service, "list_shifts", side_effect=[
                [],
                [{"id": "S1", "date": end, "status": "Yayınlandı"}],
            ]
        ), patch.object(
            bridge.workforce_service,
            "update_employment_lifecycle",
            return_value={"matched": 1, "unmatched": 0},
        ):
            with self.assertRaisesRegex(bridge.WorkforceOffboardingBridgeError, "aktif Workforce vardiyası"):
                bridge.apply_offboarding_to_workforce("EMP-1", effective_at=future, actor="hr")


if __name__ == "__main__":
    unittest.main()
