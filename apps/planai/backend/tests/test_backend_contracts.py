import os
import tempfile
import unittest


class BackendContractTests(unittest.TestCase):
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

            os.environ.pop("PLONAGRAM_AUDIT_DB", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
