import os
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from . import persistence, service
from app.modules.recruitment import service as recruitment


@unittest.skipUnless(persistence.ENABLED, "DATABASE_URL is required for PostgreSQL acceptance tests")
class WorkforcePostgresAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        service.initialize_workforce()
        recruitment.initialize()

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

    def test_v32_schema_and_row_level_tenant_isolation(self):
        self.assertGreaterEqual(persistence.schema_version(), 32)
        kind = self.unique_kind("rls")
        persistence.load_snapshot([kind])
        persistence.persist_snapshot_with_audit(
            {kind: [{"id": "ROW-1", "value": "visible-only-to-current-tenant"}]},
            "CI_RLS_WRITE",
            "ci",
        )
        with persistence.connection(persistence.MIGRATION_DATABASE_URL) as database, database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workforce_entities(tenant_id,kind,entity_id,payload)
                   VALUES ('another-tenant',%s,'ROW-OTHER','{"id":"ROW-OTHER"}'::jsonb)""",
                (kind,),
            )
            database.commit()
        with persistence.connection() as database, database.cursor() as cursor:
            persistence._set_tenant(cursor)
            cursor.execute(
                "SELECT count(*), min(tenant_id), workforce_current_tenant() FROM workforce_entities WHERE kind=%s",
                (kind,),
            )
            count, visible_tenant, bound_tenant = cursor.fetchone()
            self.assertEqual(count, 1)
            self.assertEqual(visible_tenant, persistence.TENANT_ID)
            self.assertEqual(bound_tenant, persistence.TENANT_ID)
            cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", ("another-tenant",))
            cursor.execute("SELECT count(*), workforce_current_tenant() FROM workforce_entities WHERE kind=%s", (kind,))
            spoofed_count, still_bound_tenant = cursor.fetchone()
            self.assertEqual(spoofed_count, 1)
            self.assertEqual(still_bound_tenant, persistence.TENANT_ID)

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

    def test_norm_vacancy_candidate_hire_employee_master_and_first_shift_chain(self):
        suffix = uuid4().hex[:8]
        employee_id = f"EMP-CI-{suffix}"
        tckn = str(int(uuid4().hex[:12], 16)).zfill(11)[-11:]
        warehouse_id = next(
            row["id"] for row in service.list_warehouses() if row["name"] == "Fulya (İstanbul)"
        )
        today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
        hire_date = (today - timedelta(days=2)).isoformat()
        first_shift_date = (today - timedelta(days=1)).isoformat()
        exit_date = today.isoformat()
        request = recruitment.create_request(
            {
                "warehouse_id": warehouse_id, "position_code": "STORE_STAFF", "quantity": 1,
                "employment_type": "FULL_TIME", "reason_code": "NORM_GAP",
                "needed_by": hire_date, "justification": "PostgreSQL transactional acceptance",
                "planned_departure": None,
            },
            "ci-manager", "CI Manager",
        )
        approved = recruitment.decide_request(request["id"], "APPROVED", "CI approval", "ci-hr", "CI HR")
        self.assertEqual(approved["status"], "APPROVED")
        with TemporaryDirectory() as evidence_dir, patch.object(recruitment, "_EVIDENCE_DIR", Path(evidence_dir)):
            candidate = recruitment.register_candidate(
                request["id"], {"full_name": "CI Candidate", "source_ref": f"ATS-{suffix}", "note": None}, "ci-hr"
            )
            uploaded = recruitment.add_candidate_evidence(
                request["id"], candidate["id"], "candidate.pdf", "application/pdf", b"%PDF-ci", "ci-hr"
            )
            recruitment.record_candidate_content_safety_scan(
                request["id"], candidate["id"], uploaded["evidence"][0]["sha256"],
                "CLEAN", f"AV-RECEIPT-CI-{suffix}", "scanner-ci", "scanner-service",
                provider_signature_verified=True,
            )
            recruitment.decide_candidate(request["id"], candidate["id"], "APPROVED", "Evidence accepted", "ci-hr")
            hired = recruitment.activate_hire(
                request["id"],
                {
                    "candidate_id": candidate["id"], "employee_id": employee_id,
                    "roster_ids": [f"ROSTER-{suffix}"], "full_name": "CI Candidate",
                    "tckn": tckn, "email": None, "phone": None, "employment_start": hire_date,
                    "first_shift": {"roster_id": f"ROSTER-{suffix}", "date": first_shift_date, "start": "09:00", "end": "18:00", "break_minutes": 60},
                },
                "ci-hr",
            )
        self.assertEqual(hired["activation"]["employee_master"], "ACTIVE")
        shift = hired["first_shift"]
        self.assertEqual(shift["person_id"], employee_id)
        exit_result = service.update_employment_lifecycle(
            [{"person_id": employee_id, "employment_end": exit_date}], "ci-hr", "exit.csv"
        )
        self.assertEqual(exit_result["access_closures"], 1)
        with persistence.connection() as database, database.cursor() as cursor:
            persistence._set_tenant(cursor)
            cursor.execute(
                "SELECT status,payload->>'revision' FROM recruitment_requests WHERE tenant_id=%s AND id=%s",
                (persistence.TENANT_ID, request["id"]),
            )
            status, revision = cursor.fetchone()
            self.assertEqual(status, "FILLED")
            self.assertGreaterEqual(int(revision), 6)
            cursor.execute(
                """SELECT count(*) FROM workforce_audit
                   WHERE tenant_id=%s AND event IN (
                     'RECRUITMENT_REQUEST_CREATED','RECRUITMENT_REQUEST_DECIDED',
                     'RECRUITMENT_CANDIDATE_APPROVED','RECRUITMENT_HIRE_ACTIVATED'
                   )""",
                (persistence.TENANT_ID,),
            )
            self.assertGreaterEqual(int(cursor.fetchone()[0]), 4)
            cursor.execute(
                """SELECT count(*) FROM workforce_notification_outbox
                   WHERE tenant_id=%s AND person_id=%s AND status IN ('PENDING','SENDING')""",
                (persistence.TENANT_ID, employee_id),
            )
            self.assertEqual(int(cursor.fetchone()[0]), 0)
            cursor.execute(
                """SELECT status,payload->>'reason' FROM workforce_identity_revocation_outbox
                   WHERE tenant_id=%s AND employee_id=%s""",
                (persistence.TENANT_ID, employee_id),
            )
            self.assertEqual(cursor.fetchone(), ("PENDING", "EMPLOYMENT_ENDED"))


if __name__ == "__main__":
    unittest.main()
