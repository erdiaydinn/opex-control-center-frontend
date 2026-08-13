import os
import unittest
from uuid import uuid4

from . import persistence, service


@unittest.skipUnless(persistence.ENABLED, "DATABASE_URL is required for PostgreSQL acceptance tests")
class WorkforcePostgresAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        service.initialize_workforce()

    def unique_kind(self, prefix: str) -> str:
        return f"ci_{prefix}_{uuid4().hex}"

    def audit_count(self, event: str) -> int:
        with persistence.connection() as database, database.cursor() as cursor:
            persistence._set_tenant(cursor)
            cursor.execute(
                "SELECT count(*) FROM workforce_audit WHERE tenant_id=%s AND event=%s",
                (persistence.TENANT_ID, event),
            )
            return int(cursor.fetchone()[0])

    def outbox_count(self, notification_id: str) -> int:
        with persistence.connection() as database, database.cursor() as cursor:
            persistence._set_tenant(cursor)
            cursor.execute(
                "SELECT count(*) FROM workforce_notification_outbox WHERE tenant_id=%s AND id=%s",
                (persistence.TENANT_ID, notification_id),
            )
            return int(cursor.fetchone()[0])

    def test_v29_schema_and_row_level_tenant_isolation(self):
        self.assertGreaterEqual(persistence.schema_version(), 29)
        kind = self.unique_kind("rls")
        persistence.load_snapshot([kind])
        persistence.persist_snapshot_with_audit(
            {kind: [{"id": "ROW-1", "value": "visible-only-to-current-tenant"}]},
            "CI_RLS_WRITE",
            "ci",
        )
        with persistence.connection() as database, database.cursor() as cursor:
            persistence._set_tenant(cursor)
            cursor.execute(
                "SELECT count(*) FROM workforce_entities WHERE tenant_id=%s AND kind=%s",
                (persistence.TENANT_ID, kind),
            )
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", ("another-tenant",))
            cursor.execute("SELECT count(*) FROM workforce_entities WHERE kind=%s", (kind,))
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_stale_snapshot_is_rejected_without_state_or_audit_overwrite(self):
        kind = self.unique_kind("stale")
        persistence.load_snapshot([kind])
        event = f"CI_STALE_{uuid4().hex}"
        with persistence.connection() as database, database.cursor() as cursor:
            persistence._set_tenant(cursor)
            cursor.execute(
                """INSERT INTO workforce_collection_versions(tenant_id,kind,version)
                   VALUES (%s,%s,1)
                   ON CONFLICT (tenant_id,kind) DO UPDATE SET version=workforce_collection_versions.version+1""",
                (persistence.TENANT_ID, kind),
            )
            cursor.execute(
                """INSERT INTO workforce_entities(tenant_id,kind,entity_id,payload)
                   VALUES (%s,%s,'EXTERNAL','{"id":"EXTERNAL","source":"other-instance"}'::jsonb)""",
                (persistence.TENANT_ID, kind),
            )
            database.commit()
        with self.assertRaises(persistence.ConcurrentWriteError):
            persistence.persist_snapshot_with_audit(
                {kind: [{"id": "STALE", "source": "stale-instance"}]}, event, "ci"
            )
        self.assertEqual(self.audit_count(event), 0)
        self.assertEqual(persistence.load_snapshot([kind])[kind][0]["id"], "EXTERNAL")

    def test_domain_state_and_audit_rollback_together(self):
        kind = self.unique_kind("atomic")
        persistence.load_snapshot([kind])
        persistence.persist_snapshot_with_audit(
            {kind: [{"id": "BASE", "value": 1}]}, "CI_ATOMIC_BASE", "ci"
        )
        persistence.load_snapshot([kind, "notifications"])
        failed_event = f"CI_ATOMIC_FAILED_{uuid4().hex}"
        notification_id = f"NTF-{uuid4().hex}"
        with self.assertRaises(Exception):
            persistence.persist_snapshot_with_audit(
                {
                    kind: [{"id": "DUPLICATE"}, {"id": "DUPLICATE"}],
                    "notifications": [{
                        "id": notification_id,
                        "person_id": "EMP-CI",
                        "type": "CI_ATOMIC",
                    }],
                },
                failed_event,
                "ci",
            )
        self.assertEqual(self.audit_count(failed_event), 0)
        self.assertEqual(self.outbox_count(notification_id), 0)
        rows = persistence.load_snapshot([kind])[kind]
        self.assertEqual(rows, [{"id": "BASE", "value": 1}])

    def test_device_challenge_survives_process_state_reload(self):
        challenge = service.issue_device_challenge("100184", "DEVICE-1", "ci")
        service._DEVICE_CHALLENGES.clear()
        service.initialize_workforce()
        restored = service._DEVICE_CHALLENGES.get(challenge["id"])
        self.assertIsNotNone(restored)
        self.assertEqual(restored["challenge"], challenge["challenge"])
        self.assertFalse(restored["used"])


if __name__ == "__main__":
    unittest.main()
