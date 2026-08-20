import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from .flexibility_router import _strict_employee_self


class WorkforceFlexibilityRouterTests(unittest.TestCase):
    def request(self, employee_id=None):
        identity = SimpleNamespace(employee_id=employee_id) if employee_id is not None else None
        return SimpleNamespace(state=SimpleNamespace(identity=identity))

    def test_verified_employee_cannot_act_for_another_person(self):
        with self.assertRaises(HTTPException) as raised:
            _strict_employee_self(self.request("EMP-100"), "EMP-200", "manager")
        self.assertEqual(raised.exception.status_code, 403)

    def test_production_requires_signed_employee_claim(self):
        with patch.dict("os.environ", {"DOCKOS_ENV": "production"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                _strict_employee_self(self.request(), "EMP-100", "super_admin")
        self.assertEqual(raised.exception.status_code, 403)

    def test_matching_verified_employee_passes(self):
        with patch("backend.app.modules.workforce.flexibility_router._enforce_self") as enforce:
            _strict_employee_self(self.request("EMP-100"), "EMP-100", "employee")
        enforce.assert_called_once()


if __name__ == "__main__":
    unittest.main()
