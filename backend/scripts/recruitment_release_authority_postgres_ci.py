"""Real PostgreSQL acceptance for request scanner and evidence release authorities."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg


ADMIN_URL = os.environ["RECRUITMENT_AUTHORITY_ADMIN_URL"]
TENANT = os.getenv("WORKFORCE_TENANT_ID", "eay-ci")
BACKEND = Path(__file__).resolve().parents[1]
M25 = BACKEND / "migrations" / "025_recruitment_request_evidence_scan_authority.sql"
M26 = BACKEND / "migrations" / "026_recruitment_evidence_release_authority.sql"
ROLE_PASSWORDS = {
    "eay_candidate_scanner_runtime": "candidate_scanner_ci",
    "workforce_runtime": "workforce_runtime_ci",
}


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


def apply_migrations() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=False) as database:
        execute_script(database, M25)
        execute_script(database, M26)


def request_seed() -> tuple[str, str, bytes]:
    request_id = f"REQ-RELEASE-{uuid4()}"
    evidence_id = str(uuid4())
    digest = sha256(b"request-evidence-release-proof").digest()
    payload = {
        "id": request_id,
        "status": "PENDING_APPROVAL",
        "warehouse_id": "CI-WH",
        "revision": 1,
        "evidence_required": True,
        "evidence": {
            "id": evidence_id,
            "sha256": digest.hex(),
            "storage_backend": "S3_KMS_ENVELOPE",
            "content_safety_state": "STATIC_FORMAT_ACCEPTED_AV_PENDING",
        },
        "history": [],
    }
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_requests(
                 tenant_id,id,status,warehouse_id,revision,created_at,payload
               ) VALUES(%s,%s,'PENDING_APPROVAL','CI-WH',1,now(),%s::jsonb)""",
            (TENANT, request_id, json.dumps(payload)),
        )
        database.commit()
    return request_id, evidence_id, digest


def request_scan_once(
    request_id: str,
    evidence_id: str,
    digest: bytes,
    receipt_id: str,
    result: str,
) -> tuple[bool, str | None]:
    try:
        with psycopg.connect(role_url("eay_candidate_scanner_runtime"), autocommit=False) as database, database.cursor() as cursor:
            cursor.execute(
                """SELECT recruitment.record_request_evidence_scan_receipt(
                     %s,%s,%s,%s,'ci-scanner','2026-08',%s,%s,%s,'HMAC-SHA256',%s,%s,now()
                   )""",
                (
                    TENANT,
                    uuid4(),
                    request_id,
                    evidence_id,
                    receipt_id,
                    digest,
                    result,
                    sha256(f"payload:{receipt_id}:{result}".encode()).digest(),
                    sha256(f"signature:{receipt_id}:{result}".encode()).digest(),
                ),
            )
            cursor.fetchone()
            database.commit()
            return True, None
    except psycopg.Error as error:
        return False, f"{error.sqlstate}:{str(error).splitlines()[0]}"


def request_release(request_id: str, evidence_id: str, digest: bytes) -> bool:
    with psycopg.connect(role_url("workforce_runtime")) as database, database.cursor() as cursor:
        cursor.execute(
            "SELECT recruitment.request_evidence_release_authorized(%s,%s,%s,%s)",
            (TENANT, request_id, evidence_id, digest),
        )
        return bool(cursor.fetchone()[0])


def request_authority_acceptance() -> None:
    request_id, evidence_id, digest = request_seed()
    receipt_id = f"request-replay-{uuid4()}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: request_scan_once(request_id, evidence_id, digest, receipt_id, "CLEAN"),
                range(2),
            )
        )
    assert sum(ok for ok, _ in results) == 1, results
    assert request_release(request_id, evidence_id, digest) is True

    time.sleep(0.01)
    ok, diagnostic = request_scan_once(
        request_id, evidence_id, digest, f"request-error-{uuid4()}", "ERROR"
    )
    assert ok, diagnostic
    assert request_release(request_id, evidence_id, digest) is False

    time.sleep(0.01)
    ok, diagnostic = request_scan_once(
        request_id, evidence_id, digest, f"request-clean-{uuid4()}", "CLEAN"
    )
    assert ok, diagnostic
    assert request_release(request_id, evidence_id, digest) is True

    with psycopg.connect(role_url("workforce_runtime")) as database, database.cursor() as cursor:
        cursor.execute(
            "SELECT recruitment.request_evidence_release_authorized(%s,%s,%s,%s)",
            ("other-tenant", request_id, evidence_id, digest),
        )
        assert cursor.fetchone()[0] is False
        try:
            cursor.execute("SELECT count(*) FROM recruitment.request_evidence_scan_receipts")
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("workforce_runtime has direct SELECT on request scanner authority")

    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        try:
            cursor.execute(
                """UPDATE recruitment.request_evidence_scan_receipts
                   SET result='ERROR'
                   WHERE tenant_id=%s AND request_id=%s""",
                (TENANT, request_id),
            )
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("append-only request scanner receipt was mutable")


def candidate_seed() -> tuple[str, str, str, bytes]:
    request_id = f"REQ-CAND-RELEASE-{uuid4()}"
    candidate_id = f"CAND-{uuid4()}"
    capability_id = uuid4()
    evidence_id = str(uuid4())
    digest = sha256(b"candidate-evidence-release-proof").digest()
    object_key = f"quarantine/{TENANT}/{capability_id}"
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment.candidate_upload_capabilities(
                 tenant_id,capability_id,request_id,candidate_id,token_sha256,document_type,
                 staging_object_key,max_bytes,expires_at,issued_by,consumed_at,consumed_evidence_id
               ) VALUES(%s,%s,%s,%s,%s,'OTHER',%s,10485760,now()+interval '1 day','ci',now(),%s)""",
            (
                TENANT,
                capability_id,
                request_id,
                candidate_id,
                sha256(f"token:{capability_id}".encode()).digest(),
                object_key,
                evidence_id,
            ),
        )
        cursor.execute(
            """INSERT INTO recruitment.candidate_evidence_objects(
                 tenant_id,evidence_id,capability_id,request_id,candidate_id,document_type,
                 object_key,original_name,media_type,byte_size,sha256,uploaded_at,retention_until,
                 storage_backend,storage_bucket,encryption_scheme,kms_key_id,envelope_version
               ) VALUES(
                 %s,%s,%s,%s,%s,'OTHER',%s,'candidate.pdf','application/pdf',128,%s,
                 now(),now()+interval '365 days','S3_KMS_ENVELOPE','eay-ci-evidence',
                 'AES-256-GCM+AWS-KMS-DATA-KEY','arn:aws:kms:eu-central-1:000000000000:key/ci',1
               )""",
            (TENANT, evidence_id, capability_id, request_id, candidate_id, object_key, digest),
        )
        database.commit()
    return request_id, candidate_id, evidence_id, digest


def candidate_scan_once(evidence_id: str, digest: bytes, receipt_id: str, result: str) -> tuple[bool, str | None]:
    try:
        with psycopg.connect(role_url("eay_candidate_scanner_runtime"), autocommit=False) as database, database.cursor() as cursor:
            cursor.execute(
                """SELECT recruitment.record_candidate_evidence_scan_receipt(
                     %s,%s,%s,'ci-scanner','2026-08',%s,%s,%s,'HMAC-SHA256',%s,%s,now()
                   )""",
                (
                    TENANT,
                    uuid4(),
                    evidence_id,
                    receipt_id,
                    digest,
                    result,
                    sha256(f"candidate-payload:{receipt_id}:{result}".encode()).digest(),
                    sha256(f"candidate-signature:{receipt_id}:{result}".encode()).digest(),
                ),
            )
            cursor.fetchone()
            database.commit()
            return True, None
    except psycopg.Error as error:
        return False, f"{error.sqlstate}:{str(error).splitlines()[0]}"


def candidate_release(request_id: str, candidate_id: str, evidence_id: str, digest: bytes) -> bool:
    with psycopg.connect(role_url("workforce_runtime")) as database, database.cursor() as cursor:
        cursor.execute(
            "SELECT recruitment.candidate_evidence_release_authorized(%s,%s,%s,%s,%s)",
            (TENANT, request_id, candidate_id, evidence_id, digest),
        )
        return bool(cursor.fetchone()[0])


def candidate_authority_acceptance() -> None:
    request_id, candidate_id, evidence_id, digest = candidate_seed()
    ok, diagnostic = candidate_scan_once(evidence_id, digest, f"candidate-clean-{uuid4()}", "CLEAN")
    assert ok, diagnostic
    assert candidate_release(request_id, candidate_id, evidence_id, digest) is True

    time.sleep(0.01)
    ok, diagnostic = candidate_scan_once(evidence_id, digest, f"candidate-error-{uuid4()}", "ERROR")
    assert ok, diagnostic
    assert candidate_release(request_id, candidate_id, evidence_id, digest) is False

    time.sleep(0.01)
    ok, diagnostic = candidate_scan_once(evidence_id, digest, f"candidate-clean2-{uuid4()}", "CLEAN")
    assert ok, diagnostic
    assert candidate_release(request_id, candidate_id, evidence_id, digest) is True


def schema_and_replay_contract() -> None:
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT relrowsecurity,relforcerowsecurity
               FROM pg_class
               WHERE oid='recruitment.request_evidence_scan_receipts'::regclass"""
        )
        assert cursor.fetchone() == (True, True)
        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0]) >= 42

    with psycopg.connect(ADMIN_URL, autocommit=False) as database:
        execute_script(database, M25)
        execute_script(database, M26)
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0]) >= 42


def main() -> None:
    apply_migrations()
    request_authority_acceptance()
    candidate_authority_acceptance()
    schema_and_replay_contract()
    print("recruitment V41/V42 release authority PostgreSQL acceptance: GREEN")


if __name__ == "__main__":
    main()
