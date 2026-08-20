import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from . import router


WAREHOUSES = [
    {"id": "fulya", "name": "Fulya (İstanbul)", "latitude": 41.0, "longitude": 29.0},
    {"id": "uskudar", "name": "Üsküdar (İstanbul)", "latitude": 41.02, "longitude": 29.05},
]
PEOPLE = [
    {"id": "EMP-1", "employee_id": "EMP-1", "warehouse_id": "fulya", "active": True},
    {"id": "EMP-2", "employee_id": "EMP-2", "warehouse_id": "uskudar", "active": True},
    {"id": "EMP-3", "employee_id": "EMP-3", "warehouse_id": "fulya", "active": True},
]


def request(*, employee_id=None, warehouse_scope=()):
    identity = SimpleNamespace(employee_id=employee_id, warehouse_scope=warehouse_scope)
    return SimpleNamespace(state=SimpleNamespace(identity=identity))


class WorkforceScopeHardeningTests(unittest.TestCase):
    def patches(self):
        return (
            patch.object(router, "list_warehouses", return_value=WAREHOUSES),
            patch.object(router, "list_people", return_value=PEOPLE),
        )

    def test_production_employee_gets_only_employee_master_worksite_scope(self):
        warehouse_patch, people_patch = self.patches()
        with warehouse_patch, people_patch, patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False):
            scope = router._warehouse_scope(request(employee_id="EMP-1"), "employee")
            rows = router._scoped_rows(request(employee_id="EMP-1"), "employee", WAREHOUSES)
        self.assertEqual(scope, {"fulya"})
        self.assertEqual([row["id"] for row in rows], ["fulya"])

    def test_production_employee_without_canonical_worksite_fails_closed(self):
        warehouse_patch, _ = self.patches()
        with warehouse_patch, patch.object(router, "list_people", return_value=[]), patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                router._warehouse_scope(request(employee_id="EMP-MISSING"), "employee")
        self.assertEqual(raised.exception.status_code, 403)

    def test_manager_role_cannot_impersonate_employee_on_self_service_route(self):
        with (
            patch("app.modules.workforce.service.resolve_person_identity", return_value=PEOPLE[1]),
            patch("app.modules.workforce.service.person_has_workforce_access", return_value=True),
            patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False),
        ):
            with self.assertRaises(HTTPException) as raised:
                router._enforce_self(request(employee_id="EMP-1", warehouse_scope=("fulya",)), "EMP-2", "warehouse_manager")
        self.assertEqual(raised.exception.status_code, 403)

    def test_production_self_service_requires_employee_claim_even_for_manager_role(self):
        with (
            patch("app.modules.workforce.service.resolve_person_identity", return_value=PEOPLE[0]),
            patch("app.modules.workforce.service.person_has_workforce_access", return_value=True),
            patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False),
        ):
            with self.assertRaises(HTTPException) as raised:
                router._enforce_self(request(warehouse_scope=("fulya",)), "EMP-1", "warehouse_manager")
        self.assertEqual(raised.exception.status_code, 403)

    def test_employee_announcements_exclude_other_people_sites_future_and_inactive(self):
        rows = [
            {"id": "ALL", "target_type": "all", "target_value": "", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "SELF", "target_type": "person", "target_value": "EMP-1", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "OTHER", "target_type": "person", "target_value": "EMP-2", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "OWN-WH", "target_type": "warehouse", "target_value": "fulya", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "OTHER-WH", "target_type": "warehouse", "target_value": "uskudar", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "FUTURE", "target_type": "all", "target_value": "", "publish_at": "2099-01-01T00:00:00+00:00", "active": True},
            {"id": "INACTIVE", "target_type": "all", "target_value": "", "publish_at": "2026-01-01T00:00:00+00:00", "active": False},
        ]
        warehouse_patch, people_patch = self.patches()
        with warehouse_patch, people_patch:
            visible = router._scoped_announcements(request(employee_id="EMP-1"), "employee", rows, "EMP-1")
        self.assertEqual([row["id"] for row in visible], ["ALL", "SELF", "OWN-WH"])

    def test_warehouse_manager_sees_all_plus_only_targets_inside_signed_scope(self):
        rows = [
            {"id": "ALL", "target_type": "all", "target_value": "", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "FULYA", "target_type": "warehouse", "target_value": "Fulya (İstanbul)", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "USK", "target_type": "warehouse", "target_value": "uskudar", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "FULYA-PERSON", "target_type": "person", "target_value": "EMP-3", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
            {"id": "USK-PERSON", "target_type": "person", "target_value": "EMP-2", "publish_at": "2026-01-01T00:00:00+00:00", "active": True},
        ]
        warehouse_patch, people_patch = self.patches()
        with warehouse_patch, people_patch, patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False):
            visible = router._scoped_announcements(request(warehouse_scope=("fulya",)), "warehouse_manager", rows)
        self.assertEqual([row["id"] for row in visible], ["ALL", "FULYA", "FULYA-PERSON"])


if __name__ == "__main__":
    unittest.main()
