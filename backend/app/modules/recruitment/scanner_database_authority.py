"""Dedicated PostgreSQL authority for recruitment scanner callbacks.

Production scanner writes never use the general Workforce API database identity.
The scanner service must connect with a separately provisioned, tenant-bound role
and is re-checked at runtime before any KMS-verified receipt can mutate state.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Iterator

from app.modules.workforce import persistence


class ScannerDatabaseAuthorityError(RuntimeError):
    pass


REQUIRED_SCHEMA_VERSION = 43
_DEFAULT_ROLE = "eay_candidate_scanner_runtime"


def _production() -> bool:
    return os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"


def _configured_url() -> str:
    return os.getenv("RECRUITMENT_SCANNER_DATABASE_URL", "").strip()


def _database_url() -> str:
    configured = _configured_url()
    if _production() and not configured:
        raise ScannerDatabaseAuthorityError(
            "Production recruitment scanner için dedicated PostgreSQL DSN zorunludur."
        )
    return configured or persistence.DATABASE_URL


def _expected_role() -> str:
    role = os.getenv("RECRUITMENT_SCANNER_DATABASE_ROLE", _DEFAULT_ROLE).strip()
    if not role or len(role) > 63:
        raise ScannerDatabaseAuthorityError("Scanner PostgreSQL role adı geçersiz.")
    return role


def _validate_session(cursor) -> dict:
    cursor.execute("SELECT session_user, current_user, public.workforce_current_tenant()")
    session_user, current_user, mapped_tenant = cursor.fetchone()
    expected_tenant = persistence.tenant_id()
    expected_role = _expected_role()
    if mapped_tenant != expected_tenant:
        raise ScannerDatabaseAuthorityError(
            "Scanner PostgreSQL tenant binding production otoritesiyle eşleşmiyor."
        )
    if session_user != expected_role:
        raise ScannerDatabaseAuthorityError(
            "Scanner PostgreSQL bağlantısı dedicated scanner rolüyle açılmadı."
        )
    return {
        "session_user": str(session_user),
        "current_user": str(current_user),
        "tenant_id": str(mapped_tenant),
        "expected_role": expected_role,
    }


def _connection_context():
    """Use the legacy shared connector only in local/test compatibility mode.

    Production and any explicitly configured scanner DSN always pass the dedicated
    URL. Keeping the zero-argument local path also preserves lightweight unit test
    adapters without weakening the production role boundary.
    """
    configured = _configured_url()
    if _production() or configured:
        return persistence.connection(_database_url())
    return persistence.connection()


@contextmanager
def transaction() -> Iterator[tuple[object, object]]:
    """Open the dedicated scanner transaction without masking domain failures.

    Only connection/session-attestation failures are translated to
    ``ScannerDatabaseAuthorityError``. Exceptions raised by the caller while the
    transaction is active (for example replay, digest-binding or terminal-malware
    decisions) must propagate unchanged so the security boundary cannot mislabel
    a valid fail-closed business rejection as a database-authority outage.
    """
    if not persistence.ENABLED:
        raise ScannerDatabaseAuthorityError("PostgreSQL persistence yapılandırılmadı.")
    if _production() and (persistence.schema_version() or 0) < REQUIRED_SCHEMA_VERSION:
        raise ScannerDatabaseAuthorityError(
            f"Recruitment scanner PostgreSQL V{REQUIRED_SCHEMA_VERSION} olmadan çalışamaz."
        )

    try:
        connection_context = _connection_context()
    except ScannerDatabaseAuthorityError:
        raise
    except Exception as error:
        raise ScannerDatabaseAuthorityError(
            "Dedicated scanner PostgreSQL authority doğrulanamadı."
        ) from error

    with connection_context as database, database.cursor() as cursor:
        try:
            persistence._set_tenant(cursor)
            # Existing unit/local adapters may share the main DB connection; role
            # attestation becomes mandatory as soon as production or an explicit
            # scanner DSN is selected.
            if _production() or _configured_url():
                _validate_session(cursor)
        except ScannerDatabaseAuthorityError:
            raise
        except Exception as error:
            raise ScannerDatabaseAuthorityError(
                "Dedicated scanner PostgreSQL authority doğrulanamadı."
            ) from error

        # Deliberately outside the setup try/except: caller/domain exceptions
        # propagate with their original security semantics. The DB context manager
        # still rolls the transaction back when they escape this yield.
        yield database, cursor


def live_preflight() -> dict:
    """Prove the production scanner role shape without recording a receipt."""
    if not _configured_url():
        raise ScannerDatabaseAuthorityError("Dedicated scanner PostgreSQL DSN yapılandırılmadı.")
    if not persistence.ENABLED or (persistence.schema_version() or 0) < REQUIRED_SCHEMA_VERSION:
        raise ScannerDatabaseAuthorityError(
            f"Recruitment scanner PostgreSQL V{REQUIRED_SCHEMA_VERSION} hazır değil."
        )
    with persistence.connection(_database_url()) as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        identity = _validate_session(cursor)
        cursor.execute(
            """SELECT
                 has_function_privilege(current_user,
                   'recruitment.get_candidate_evidence_scan_binding(text,uuid)','EXECUTE'),
                 has_function_privilege(current_user,
                   'recruitment.record_candidate_evidence_scan_receipt(text,uuid,uuid,text,text,text,bytea,text,text,bytea,bytea,timestamptz)','EXECUTE'),
                 has_function_privilege(current_user,
                   'recruitment.record_request_evidence_scan_receipt(text,uuid,text,uuid,text,text,text,bytea,text,text,bytea,bytea,timestamptz)','EXECUTE'),
                 has_column_privilege(current_user,'public.recruitment_requests','payload','SELECT'),
                 has_column_privilege(current_user,'public.recruitment_requests','payload','UPDATE'),
                 has_table_privilege(current_user,'public.recruitment_settings','UPDATE'),
                 has_table_privilege(current_user,'public.recruitment_norms','UPDATE')"""
        )
        (
            binding_exec,
            candidate_receipt_exec,
            request_receipt_exec,
            request_payload_select,
            request_payload_update,
            settings_update,
            norms_update,
        ) = cursor.fetchone()
        database.rollback()
    required = all(
        (
            binding_exec,
            candidate_receipt_exec,
            request_receipt_exec,
            request_payload_select,
            request_payload_update,
        )
    )
    overprivileged = bool(settings_update or norms_update)
    if not required or overprivileged:
        raise ScannerDatabaseAuthorityError(
            "Scanner PostgreSQL role least-privilege sözleşmesini karşılamıyor."
        )
    return {
        **identity,
        "schema_required": REQUIRED_SCHEMA_VERSION,
        "dedicated_dsn": True,
        "receipt_functions": 3,
        "request_projection_write": True,
        "hr_settings_write": False,
        "hr_norms_write": False,
        "truth_boundary": "DEDICATED_TENANT_BOUND_SCANNER_DB_ROLE",
    }
