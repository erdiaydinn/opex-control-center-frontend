import os
import tempfile
import unittest


class BackendContractTests(unittest.TestCase):
    def test_store_master_contains_full_depot_inventory_and_fulya_dna(self):
        from store_dna_store import default_dna, list_stores

        stores = list_stores()
        self.assertGreaterEqual(len(stores), 110)
        self.assertEqual(len(stores), len({item["store_code"] for item in stores}))

        fulya = default_dna("FULYA")
        self.assertIsNotNone(fulya)
        self.assertEqual(fulya["store_name"], "Fulya (İstanbul)")
        self.assertEqual(fulya["martek_plus4_count"], 9)
        self.assertEqual(fulya["martek_frozen_count"], 1)
        self.assertEqual(fulya["algida_count"], 7)
        self.assertEqual(fulya["aisle_count"], 10)
        self.assertTrue(fulya["layout_objects"])

    def test_opex_action_claims_override_legacy_role_without_escalation(self):
        from security import can_action

        viewer = {
            "role": "VIEWER",
            "permissions": {
                "actions": {
                    "view": True,
                    "create": False,
                    "edit": False,
                }
            },
        }
        self.assertTrue(can_action(viewer, "view"))
        self.assertFalse(can_action(viewer, "create"))
        self.assertFalse(can_action(viewer, "edit"))

    def test_opex_dev_bridge_is_never_enabled_in_production(self):
        import importlib
        import auth_routes

        old_env = os.environ.get("PLONAGRAM_ENV")
        old_bridge = os.environ.get("PLONAGRAM_OPEX_DEV_BRIDGE")
        try:
            os.environ["PLONAGRAM_ENV"] = "production"
            os.environ["PLONAGRAM_OPEX_DEV_BRIDGE"] = "true"
            auth_routes = importlib.reload(auth_routes)
            self.assertFalse(auth_routes._opex_dev_bridge_enabled())
        finally:
            if old_env is None:
                os.environ.pop("PLONAGRAM_ENV", None)
            else:
                os.environ["PLONAGRAM_ENV"] = old_env
            if old_bridge is None:
                os.environ.pop("PLONAGRAM_OPEX_DEV_BRIDGE", None)
            else:
                os.environ["PLONAGRAM_OPEX_DEV_BRIDGE"] = old_bridge

    def test_opex_dev_exchange_mints_scoped_action_token(self):
        from types import SimpleNamespace
        import auth_routes
        from security import decode_token

        old_values = {
            key: os.environ.get(key)
            for key in (
                "PLONAGRAM_ENV",
                "PLONAGRAM_OPEX_DEV_BRIDGE",
                "PLONAGRAM_AUTH_SECRET",
            )
        }
        try:
            os.environ["PLONAGRAM_ENV"] = "development"
            os.environ["PLONAGRAM_OPEX_DEV_BRIDGE"] = "true"
            os.environ["PLONAGRAM_AUTH_SECRET"] = "test-secret-not-for-production"
            response = auth_routes.opex_dev_exchange(
                auth_routes.OpexBridgeRequest(**{
                    "user": {
                        "email": "viewer@yemeksepeti.com",
                        "name": "Viewer",
                        "role": "viewer",
                    },
                    "permissions": {
                        "view": True,
                        "admin": False,
                        "features": {"layoutView": True, "layoutEdit": False},
                        "actions": {"view": True, "create": False, "edit": False},
                    },
                    "scope": {
                        "type": "warehouse",
                        "warehouses": ["FULYA"],
                    },
                }),
                SimpleNamespace(headers={"origin": "http://localhost:5174"}),
            )
            claims = decode_token(response["access_token"])
            self.assertEqual(claims["email"], "viewer@yemeksepeti.com")
            self.assertEqual(claims["assigned_stores"], ["FULYA"])
            self.assertFalse(claims["permissions"]["actions"]["edit"])
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_rule_catalog_accepts_operational_cold_labels_and_rejects_overlap(self):
        from rule_catalog import validate_rule_payload

        valid = validate_rule_payload({
            "allowed_storage_type": "+4",
            "allowed_categories": "Dairy, Yogurt",
        })
        self.assertTrue(valid["valid"])

        invalid = validate_rule_payload({
            "allowed_categories": ["Beverage"],
            "blocked_categories": ["Beverage"],
        })
        self.assertFalse(invalid["valid"])
        self.assertTrue(invalid["errors"])

    def test_audit_log_supports_action_actor_store_and_date_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "audit.sqlite3")
            os.environ["PLONAGRAM_AUDIT_DB"] = db_path

            # Import after setting the environment variable so the test never
            # touches a developer's local PlanAI data directory.
            import importlib
            import audit_store
            audit_store = importlib.reload(audit_store)

            audit_store.write_audit(
                "plan_generated",
                actor="erdi",
                store_code="FULYA",
                request_id="req-1",
            )
            audit_store.write_audit(
                "shelf_reordered",
                actor="other",
                store_code="ANKA",
                request_id="req-2",
            )

            result = audit_store.list_audit_logs(
                action="plan_generated",
                actor="erdi",
                store_code="FULYA",
                request_id="req-1",
                created_from="2000-01-01",
                created_to="2999-12-31",
            )
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["logs"][0]["action"], "plan_generated")
            search_result = audit_store.list_audit_logs(q="FUL", created_from="2000-01-01")
            self.assertEqual(search_result["total"], 1)
            self.assertEqual(search_result["logs"][0]["store_code"], "FULYA")

            os.environ.pop("PLONAGRAM_AUDIT_DB", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
