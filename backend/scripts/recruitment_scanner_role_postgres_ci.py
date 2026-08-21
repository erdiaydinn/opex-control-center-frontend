"""Real PostgreSQL V43 acceptance for scanner separation of duties."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg


ADMIN_URL = os.environ["RECRUITMENT_AUTHORITY_ADMIN_URL"]
TENANT = os.getenv("WORKFORCE_TENANT_ID", "eay-ci")
BACKEND = Path(__file__).resolve().parents[1]
M43 = BACKEND / "migrations" / "027_recruitment_scanner_role_isolation.sql"
PASSWORDS = {
    "workforce_runtime": "workforce_runtime_ci",
    "eay_candidate_scanner_runtime": "candidate_scanner_ci",
}


def role_url(role: str) -> str:
    parsed = urlsplit(ADMIN_URL)
    host = parsed.hostname or "localhost"
    host = f"{host}:{parsed.port}" if parsed.port else host
    return urlunsplit(
        (
            parsed.scheme,
            f"{quote(role)}:{quote(PASSWORDS[role])}@{host}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def apply_v43() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(M43.read_text(encoding="utf-8"))
        database.commit()


def role_shape() -> None:
    candidate_sig = (
        "recruitment.record_candidate_evidence_scan_receipt("
        "text,uuid,uuid,text,text,text,bytea,text,text,bytea,bytea,timestamptz)"
    )
    request_sig = (
        "recruitment.record_request_evidence_scan_receipt("
        "text,uuid,text,uuid,text,text,text,bytea,text,text,bytea,bytea,timestamptz)"
    )
    binding_sig = "recruitment.get_candidate_evidence_scan_binding(text,uuid)"
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolbypassrls
               FROM pg_roles
               WHERE rolname IN ('workforce_runtime','eay_candidate_scanner_runtime')
               ORDER BY rolname"""
        )
        rows = cursor.fetchall()
        assert len(rows) == 2, rows
        for row in rows:
            assert row[1:] == (False, False, False, False), row

        for signature in (binding_sig, candidate_sig, request_sig):
            cursor.execute(
                "SELECT has_function_privilege('workforce_runtime',%s,'EXECUTE')",
                (signature,),
            )
            assert cursor.fetchone()[0] is False, signature
            cursor.execute(
                "SELECT has_function_privilege('eay_candidate_scanner_runtime',%s,'EXECUTE')",
                (signature,),
            )
            assert cursor.fetchone()[0] is True, signature

        cursor.execute(
            "SELECT has_function_privilege('eay_candidate_scanner_runtime',"
            "'recruitment.candidate_evidence_release_authorized(text,text,text,uuid,bytea)','EXECUTE')"
        )
        assert cursor.fetchone()[0] is False
        cursor.execute(
            "SELECT has_function_privilege('eay_candidate_scanner_runtime',"
            "'recruitment.request_evidence_release_authorized(text,text,uuid,bytea)','EXECUTE')"
        )
        assert cursor.fetchone()[0] is False


def tenant_rls_and_column_scope() -> None:
    own_id = f"REQ-V43-{uuid4()}"
    other_id = f"REQ-V43-OTHER-{uuid4()}"
    payload = {"id": own_id, "revision": 1, "history": []}
    other_payload = {"id": other_id, "revision": 1, "history": []}
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_requests(
                 tenant_id,id,status,warehouse_id,revision,created_at,payload
               ) VALUES(%s,%s,'PENDING_APPROVAL','CI-WH',1,now(),%s::jsonb),
                       ('other-tenant',%s,'PENDING_APPROVAL','OTHER',1,now(),%s::jsonb)""",
            (TENANT, own_id, json.dumps(payload), other_id, json.dumps(other_payload)),
        )
        database.commit()

    with psycopg.connect(role_url("eay_candidate_scanner_runtime"), autocommit=False) as database, database.cursor() as cursor:
        cursor.execute("SELECT session_user,current_user,workforce_current_tenant()")
        session_user, current_user, mapped = cursor.fetchone()
        assert session_user == "eay_candidate_scanner_runtime"
        assert current_user == "eay_candidate_scanner_runtime"
        assert mapped == TENANT
        cursor.execute("SELECT set_config('app.workforce_tenant','other-tenant',true)")
        cursor.execute("SELECT workforce_current_tenant()")
        assert cursor.fetchone()[0] == TENANT

        cursor.execute(
            "SELECT id FROM recruitment_requests WHERE id=ANY(%s) ORDER BY id",
            ([own_id, other_id],),
        )
        assert [row[0] for row in cursor.fetchall()] == [own_id]

        cursor.execute(
            """UPDATE recruitment_requests
               SET revision=revision+1,payload=jsonb_set(payload,'{scanner_probe}','true'::jsonb,true)
               WHERE tenant_id=%s AND id=%s""",
            (TENANT, own_id),
        )
        assert cursor.rowcount == 1
        database.commit()

    with psycopg.connect(role_url("eay_candidate_scanner_runtime"), autocommit=False) as database, database.cursor() as cursor:
        try:
            cursor.execute(
                "UPDATE recruitment_requests SET status='APPROVED' WHERE tenant_id=%s AND id=%s",
                (TENANT, own_id),
            )
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("scanner role could mutate recruitment status")

        try:
            cursor.execute("UPDATE recruitment_settings SET payload='{}'::jsonb")
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("scanner role could mutate recruitment settings")

        try:
            cursor.execute("UPDATE recruitment_norms SET payload='{}'::jsonb")
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("scanner role could mutate recruitment norms")


def replay_contract() -> None:
    apply_v43()
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0]) >= 43


def main() -> None:
    apply_v43()
    role_shape()
    tenant_rls_and_column_scope()
    replay_contract()
    print("recruitment V43 dedicated scanner PostgreSQL acceptance: GREEN")


if __name__ == "__main__":
    main()
