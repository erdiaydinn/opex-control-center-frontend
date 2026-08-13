"""Fail CI unless a restored PostgreSQL copy retains V31 and audit truth."""

import os

import psycopg


source_url = os.environ["WORKFORCE_MIGRATION_DATABASE_URL"]
restore_url = os.environ["WORKFORCE_RESTORE_DATABASE_URL"]


def facts(database_url: str) -> tuple[int, int, int]:
    with psycopg.connect(database_url) as database, database.cursor() as cursor:
        cursor.execute("SELECT COALESCE(max(version),0) FROM workforce_schema_migrations")
        version = int(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM workforce_audit")
        audit_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM workforce_collection_versions")
        collection_count = int(cursor.fetchone()[0])
        return version, audit_count, collection_count


source = facts(source_url)
restored = facts(restore_url)
if source[0] < 31 or restored != source:
    raise SystemExit(f"restore verification failed: source={source} restored={restored}")
print(f"restore verified: schema=V{restored[0]} audit={restored[1]} collections={restored[2]}")
