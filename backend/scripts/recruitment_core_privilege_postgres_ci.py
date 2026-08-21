"""Prove V40 does not break the core Hiring runtime while sealing authority tables."""
from __future__ import annotations

import os

import psycopg


ADMIN_URL = os.environ["RECRUITMENT_AUTHORITY_ADMIN_URL"]
RUNTIME_URL = os.environ["DATABASE_URL"]
TENANT = os.getenv("WORKFORCE_TENANT_ID", "eay-ci")


def main() -> None:
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        for table in ("recruitment_requests", "recruitment_email_outbox"):
            for privilege in ("SELECT", "INSERT", "UPDATE"):
                cursor.execute(
                    "SELECT has_table_privilege('workforce_runtime', %s, %s)",
                    (table, privilege),
                )
                assert cursor.fetchone()[0] is True, (table, privilege)

        for table in (
            "recruitment.candidate_upload_capabilities",
            "recruitment.candidate_evidence_objects",
            "recruitment.candidate_evidence_scan_receipts",
        ):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cursor.execute(
                    "SELECT has_table_privilege('workforce_runtime', %s, %s)",
                    (table, privilege),
                )
                assert cursor.fetchone()[0] is False, (table, privilege)

        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0]) >= 40

    # Prove the actual application login can still execute its core reads after V40.
    with psycopg.connect(RUNTIME_URL) as database, database.cursor() as cursor:
        cursor.execute("SELECT workforce_current_tenant()")
        assert cursor.fetchone()[0] == TENANT
        cursor.execute(
            "SELECT count(*) FROM recruitment_requests WHERE tenant_id=%s",
            (TENANT,),
        )
        assert cursor.fetchone()[0] >= 0
        cursor.execute(
            "SELECT count(*) FROM recruitment_email_outbox WHERE tenant_id=%s",
            (TENANT,),
        )
        assert cursor.fetchone()[0] >= 0

    print("recruitment V40 core/authority privilege acceptance: GREEN")


if __name__ == "__main__":
    main()
