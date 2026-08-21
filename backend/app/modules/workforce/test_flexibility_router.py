import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from . import flexibility_router


class WorkforceFlexibilityRouterTests(unittest.TestCase):
    def request(self, employee_id=None):
        identity = SimpleNamespace(employee_id=employee_id) if employee_id is not None else None
        return SimpleNamespace(state=SimpleNamespace(identity=identity))

    def test_verified_employee_cannot_act_for_another_person(self):
        with self.assertRaises(HTTPException) as raised:
            flexibility_router._strict_employee_self(self.request("EMP-100"), "EMP-200", "manager")
        self.assertEqual(raised.exception.status_code, 403)

    def test_production_requires_signed_employee_claim(self):
        with patch.dict("os.environ", {"DOCKOS_ENV": "production"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                flexibility_router._strict_employee_self(self.request(), "EMP-100", "super_admin")
        self.assertEqual(raised.exception.status_code, 403)

    def test_matching_verified_employee_passes(self):
        request = self.request("EMP-100")
        with patch.object(flexibility_router, "_enforce_self") as enforce:
            flexibility_router._strict_employee_self(request, "EMP-100", "employee")
        enforce.assert_called_once_with(request, "EMP-100", "employee")

    def test_open_shift_feed_uses_explainable_soft_ranking_after_self_scope(self):
        request = self.request("EMP-100")
        ranked = [
            {
                "id": "OPEN-1",
                "eligibility": {
                    "eligible": True,
                    "assignment_ranking": {
                        "soft_only": True,
                        "fairness_score": 92,
                        "fatigue_risk_score": 8,
                    },
                },
            }
        ]
        with (
            patch.object(flexibility_router, "_enforce_self") as enforce,
            patch.object(
                flexibility_router,
                "list_ranked_open_shifts_for_person",
                return_value=ranked,
            ) as ranker,
        ):
            result = flexibility_router.get_open_shifts(
                person_id="EMP-100",
                request=request,
                x_opex_role="employee",
            )
        enforce.assert_called_once_with(request, "EMP-100", "employee")
        ranker.assert_called_once_with("EMP-100")
        self.assertEqual(result, {"rows": ranked})
        self.assertTrue(result["rows"][0]["eligibility"]["assignment_ranking"]["soft_only"])

    def test_staffing_norm_manager_can_read_activity_and_labor_catalog_without_create_shift(self):
        activities = [{"activity_key": "checkout_service"}]
        standards = [{"activity_key": "checkout_service", "seconds_per_unit": "90"}]
        with (
            patch.object(flexibility_router, "list_activity_catalog", return_value=activities),
            patch.object(flexibility_router, "list_labor_standards", return_value=standards),
        ):
            activity_result = flexibility_router.get_activity_catalog(
                x_opex_role="viewer",
                x_opex_permissions="manageStaffingNorms",
            )
            labor_result = flexibility_router.get_labor_standards(
                activity_key=None,
                x_opex_role="viewer",
                x_opex_permissions="manageStaffingNorms",
            )
        self.assertEqual(activity_result["rows"], activities)
        self.assertEqual(labor_result["rows"], standards)

    def test_system_config_manager_can_read_catalog_without_create_shift(self):
        with patch.object(flexibility_router, "list_activity_catalog", return_value=[]):
            result = flexibility_router.get_activity_catalog(
                x_opex_role="viewer",
                x_opex_permissions="manageSystemConfig",
            )
        self.assertEqual(result, {"rows": []})

    def test_catalog_read_stays_closed_for_unprivileged_viewer(self):
        with self.assertRaises(HTTPException) as raised:
            flexibility_router.get_activity_catalog(
                x_opex_role="viewer",
                x_opex_permissions="",
            )
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
