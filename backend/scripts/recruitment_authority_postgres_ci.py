"""Real PostgreSQL acceptance for recruitment production authorities.

This suite deliberately uses separate login sessions and concurrent transactions.
It proves role shape, FORCE RLS, tenant binding, failed-finalize rollback, one-time
upload consumption, scanner receipt replay rejection, and migration replay.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg


ADMIN_URL = os.environ["RECRUITMENT_AUTHORITY_ADMIN_URL"]
TENANT = os.getenv("WORKFORCE_TENANT_ID", "eay-ci")
ROLE_PASSWORDS = {
    "eay_candidate_upload_runtime": "candidate_upload_ci",
    "eay_recruitment_runtime": "recruitment_ci",
    "eay_candidate_scanner_runtime": "candidate_scanner_ci",
    "eay_rls_probe": "rls_probe_ci",
}
BACKEND = Path(__file__).resolve().parents[1]
M23 = BACKEND / "migrations" / "023_recruitment_candidate_upload_authority.sql"
M24 = BACKEND / "migrations" / "024_recruitment_production_authority.sql"
KMS_ARN = "arn:aws:kms:eu-central-1:000000000000:key/ci"


def role_url(role: str) -> str:
    parsed = urlsplit(ADMIN_URL)
    host = parsed.hostname or "localhost"
    host = f"{host}:{parsed.port}" if parsed.port else host
    return urlunsplit(
        (
            parsed.scheme,
            f"{quote(role)}:{quote(ROLE_PASSWORDS[role])}@{host}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def execute_script(database, path: Path) -> None:
    with database.cursor() as cursor:
        cursor.execute(path.read_text(encoding="utf-8"))
    database.commit()


def bootstrap() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=False) as database:
        with database.cursor() as cursor:
            for role, password in ROLE_PASSWORDS.items():
                cursor.execute(
                    f"""DO $do$
                    BEGIN
                      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                        CREATE ROLE {role} LOGIN PASSWORD '{password}'
                          NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
                      END IF;
                    END
                    $do$;"""
                )
            cursor.execute(
                """INSERT INTO workforce_tenant_bindings(role_name,tenant_id)
                   VALUES
                     ('eay_candidate_upload_runtime',%s),
                     ('eay_recruitment_runtime',%s),
                     ('eay_candidate_scanner_runtime',%s),
                     ('eay_rls_probe',%s)
                   ON CONFLICT(role_name) DO UPDATE SET tenant_id=EXCLUDED.tenant_id""",
                (TENANT, TENANT, TENANT, TENANT),
            )
            cursor.execute(
                "GRANT CONNECT ON DATABASE workforce_ci TO "
                "eay_candidate_upload_runtime,eay_recruitment_runtime,"
                "eay_candidate_scanner_runtime,eay_rls_probe"
            )
        database.commit()
        execute_script(database, M23)
        execute_script(database, M24)
        with database.cursor() as cursor:
            cursor.execute("GRANT USAGE ON SCHEMA recruitment TO eay_rls_probe")
            cursor.execute(
                """GRANT SELECT ON
                     recruitment.candidate_upload_capabilities,
                     recruitment.candidate_evidence_objects,
                     recruitment.candidate_evidence_scan_receipts
                   TO eay_rls_probe"""
            )
        database.commit()


def seed(tenant: str, token_digest: bytes) -> str:
    capability_id = uuid4()
    object_key = f"quarantine/{tenant}/{capability_id}"
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment.candidate_upload_capabilities(
                 tenant_id,capability_id,request_id,candidate_id,token_sha256,
                 document_type,staging_object_key,max_bytes,expires_at,issued_by
               ) VALUES(%s,%s,%s,%s,%s,'RESIDENCE',%s,10485760,
                        now()+interval '15 minutes','ci')""",
            (
                tenant,
                capability_id,
                f"REQ-{capability_id}",
                f"CAND-{capability_id}",
                token_digest,
                object_key,
            ),
        )
        database.commit()
    return str(capability_id)


def role_and_rls_contract() -> None:
    seed("other-tenant", sha256(b"other-tenant-capability").digest())
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls
               FROM pg_roles WHERE rolname=ANY(%s) ORDER BY rolname""",
            (list(ROLE_PASSWORDS),),
        )
        rows = cursor.fetchall()
        assert len(rows) == len(ROLE_PASSWORDS), rows
        for row in rows:
            _, superuser, createdb, createrole, inherit, bypassrls = row
            assert not superuser and not createdb and not createrole and not inherit and not bypassrls, row
        cursor.execute(
            """SELECT relname,relrowsecurity,relforcerowsecurity
               FROM pg_class
               WHERE oid=ANY(ARRAY[
                 'recruitment.candidate_upload_capabilities'::regclass,
                 'recruitment.candidate_evidence_objects'::regclass,
                 'recruitment.candidate_evidence_scan_receipts'::regclass
               ]::oid[])"""
        )
        for relname, rls, force_rls in cursor.fetchall():
            assert rls and force_rls, (relname, rls, force_rls)

    with psycopg.connect(role_url("eay_candidate_upload_runtime")) as database, database.cursor() as cursor:
        cursor.execute("SELECT workforce_current_tenant()")
        assert cursor.fetchone()[0] == TENANT
        cursor.execute("SELECT set_config('app.workforce_tenant','other-tenant',true)")
        cursor.execute("SELECT workforce_current_tenant()")
        assert cursor.fetchone()[0] == TENANT
        cursor.execute(
            "SELECT has_function_privilege(current_user, "
            "'recruitment.finalize_candidate_evidence_upload(text,bytea,text,uuid,text,text,bigint,bytea,timestamptz)', "
            "'EXECUTE')"
        )
        assert cursor.fetchone()[0] is False
        try:
            cursor.execute("SELECT count(*) FROM recruitment.candidate_upload_capabilities")
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("upload role has direct SELECT on authority table")

    with psycopg.connect(role_url("eay_rls_probe")) as database, database.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM recruitment.candidate_upload_capabilities")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT set_config('app.workforce_tenant','other-tenant',true)")
        cursor.execute("SELECT count(*) FROM recruitment.candidate_upload_capabilities")
        assert cursor.fetchone()[0] == 0


def finalize_once(token: bytes, evidence_id: str, evidence_sha: bytes) -> tuple[bool, str | None]:
    try:
        with psycopg.connect(
            role_url("eay_candidate_upload_runtime"), autocommit=False
        ) as database, database.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM recruitment.finalize_candidate_evidence_upload_v2(
                     %s,%s,'RESIDENCE',%s,'residence.pdf','application/pdf',128,%s,
                     now()+interval '365 days','eay-ci-evidence',
                     'AES-256-GCM+AWS-KMS-DATA-KEY',%s,1
                   )""",
                (TENANT, token, evidence_id, evidence_sha, KMS_ARN),
            )
            ok = cursor.fetchone() is not None
            database.commit()
            return ok, None
    except psycopg.Error as error:
        return False, f"{error.sqlstate}:{str(error).splitlines()[0]}"


def failed_finalize_rolls_back() -> None:
    token = sha256(b"rollback-capability").digest()
    capability_id = seed(TENANT, token)
    digest = sha256(b"%PDF-1.7\nrollback-proof").digest()
    evidence_id = str(uuid4())
    try:
        with psycopg.connect(
            role_url("eay_candidate_upload_runtime"), autocommit=False
        ) as database, database.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM recruitment.finalize_candidate_evidence_upload_v2(
                     %s,%s,'RESIDENCE',%s,'residence.pdf','application/pdf',128,%s,
                     now()+interval '365 days','',
                     'AES-256-GCM+AWS-KMS-DATA-KEY',%s,1
                   )""",
                (TENANT, token, evidence_id, digest, KMS_ARN),
            )
    except psycopg.Error:
        pass
    else:
        raise AssertionError("invalid storage metadata finalized")

    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT consumed_at,consumed_evidence_id
               FROM recruitment.candidate_upload_capabilities
               WHERE tenant_id=%s AND capability_id=%s""",
            (TENANT, capability_id),
        )
        assert cursor.fetchone() == (None, None)
        cursor.execute(
            """SELECT count(*) FROM recruitment.candidate_evidence_objects
               WHERE tenant_id=%s AND capability_id=%s""",
            (TENANT, capability_id),
        )
        assert cursor.fetchone()[0] == 0

    ok, diagnostic = finalize_once(token, evidence_id, digest)
    assert ok, diagnostic


def upload_replay() -> tuple[str, bytes]:
    token = sha256(b"single-use").digest()
    capability_id = seed(TENANT, token)
    digest = sha256(b"%PDF-1.7\nci-evidence").digest()
    evidence_ids = [str(uuid4()), str(uuid4())]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda evidence_id: finalize_once(token, evidence_id, digest), evidence_ids))
    assert sum(ok for ok, _ in results) == 1, results

    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT evidence_id,storage_backend,encryption_scheme,envelope_version
               FROM recruitment.candidate_evidence_objects
               WHERE tenant_id=%s AND capability_id=%s""",
            (TENANT, capability_id),
        )
        rows = cursor.fetchall()
        assert len(rows) == 1, rows
        row = rows[0]
        assert row[1:] == ("S3_KMS_ENVELOPE", "AES-256-GCM+AWS-KMS-DATA-KEY", 1), row
        cursor.execute(
            """SELECT consumed_at,consumed_evidence_id
               FROM recruitment.candidate_upload_capabilities
               WHERE tenant_id=%s AND capability_id=%s""",
            (TENANT, capability_id),
        )
        consumed_at, consumed_evidence_id = cursor.fetchone()
        assert consumed_at is not None and str(consumed_evidence_id) == str(row[0])
        return str(row[0]), digest


def scan_once(evidence_id: str, digest: bytes, receipt_id: str) -> tuple[bool, str | None]:
    try:
        with psycopg.connect(
            role_url("eay_candidate_scanner_runtime"), autocommit=False
        ) as database, database.cursor() as cursor:
            cursor.execute(
                """SELECT recruitment.record_candidate_evidence_scan_receipt(
                     %s,%s,%s,'ci-scanner','2026-08',%s,%s,'CLEAN','HMAC-SHA256',
                     %s,%s,now()
                   )""",
                (
                    TENANT,
                    uuid4(),
                    evidence_id,
                    receipt_id,
                    digest,
                    sha256(b"payload").digest(),
                    sha256(b"signature").digest(),
                ),
            )
            cursor.fetchone()
            database.commit()
            return True, None
    except psycopg.Error as error:
        return False, f"{error.sqlstate}:{str(error).splitlines()[0]}"


def scanner_replay(evidence_id: str, digest: bytes) -> None:
    receipt_id = f"receipt-{uuid4()}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: scan_once(evidence_id, digest, receipt_id), range(2)))
    assert sum(ok for ok, _ in results) == 1, results
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT count(*) FROM recruitment.candidate_evidence_scan_receipts
               WHERE tenant_id=%s AND provider='ci-scanner' AND receipt_id=%s""",
            (TENANT, receipt_id),
        )
        assert cursor.fetchone()[0] == 1


def cross_tenant_rejected() -> None:
    with psycopg.connect(
        role_url("eay_candidate_upload_runtime"), autocommit=False
    ) as database, database.cursor() as cursor:
        try:
            cursor.execute(
                "SELECT * FROM recruitment.prepare_candidate_evidence_upload(%s,%s,'RESIDENCE',128,%s)",
                ("other-tenant", sha256(b"x").digest(), sha256(b"y").digest()),
            )
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("cross-tenant prepare succeeded")


def replay_migration() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=False) as database:
        execute_script(database, M24)
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0]) >= 40


def main() -> None:
    bootstrap()
    role_and_rls_contract()
    cross_tenant_rejected()
    failed_finalize_rolls_back()
    evidence_id, digest = upload_replay()
    scanner_replay(evidence_id, digest)
    replay_migration()
    print("recruitment production authority PostgreSQL acceptance: GREEN")


if __name__ == "__main__":
    main()
