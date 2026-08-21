"""Resource ownership lookups for request-scoped recruitment authorization."""
from __future__ import annotations

from uuid import UUID

from app.modules.workforce import persistence


class RecruitmentScopeError(ValueError):
    pass


def _uuid(value: str, label: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as error:
        raise RecruitmentScopeError(f"{label} kimliği geçersiz.") from error


def offer_request_id(offer_id: str) -> str:
    offer_uuid = _uuid(offer_id, "Offer")
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT request_id FROM recruitment.offer_packages WHERE tenant_id=%s AND offer_id=%s",
            (persistence.tenant_id(), offer_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentScopeError("Offer bulunamadı.")
        return str(row[0])


def onboarding_task_scope(task_id: str) -> tuple[str, str]:
    task_uuid = _uuid(task_id, "Onboarding task")
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT request_id,owner_role FROM recruitment.onboarding_tasks
               WHERE tenant_id=%s AND task_id=%s""",
            (persistence.tenant_id(), task_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentScopeError("Onboarding task bulunamadı.")
        return str(row[0]), str(row[1])
