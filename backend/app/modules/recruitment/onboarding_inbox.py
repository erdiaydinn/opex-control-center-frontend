"""Owner-scoped onboarding work queue.

The inbox is deliberately separate from the HR recruitment workspace: IT, Academy,
Admin and Operations users must be able to complete only the tasks assigned to
their function without receiving broad recruitment visibility.
"""
from __future__ import annotations

from app.modules.workforce import persistence


class OnboardingInboxError(RuntimeError):
    pass


REQUIRED_SCHEMA_VERSION = 46


def list_owner_tasks(owner_roles: set[str], *, include_terminal: bool = False) -> list[dict]:
    if not owner_roles:
        return []
    if not persistence.ENABLED or (persistence.schema_version() or 0) < REQUIRED_SCHEMA_VERSION:
        raise OnboardingInboxError(
            f"Recruitment onboarding inbox PostgreSQL V{REQUIRED_SCHEMA_VERSION} olmadan kullanılamaz."
        )
    normalized = sorted({str(value).strip().upper() for value in owner_roles if str(value).strip()})
    if not normalized:
        return []
    terminal_clause = "" if include_terminal else "AND t.status NOT IN ('COMPLETED','WAIVED')"
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            f"""SELECT t.task_id,t.request_id,t.candidate_id,t.offer_id,t.task_key,t.title,
                       t.owner_role,t.required,t.due_at,t.dependencies,t.status,t.revision,
                       r.warehouse_id,r.payload
                FROM recruitment.onboarding_tasks t
                JOIN public.recruitment_requests r
                  ON r.tenant_id=t.tenant_id AND r.id=t.request_id
                WHERE t.tenant_id=%s AND t.owner_role=ANY(%s) {terminal_clause}
                ORDER BY (t.due_at IS NULL),t.due_at,t.created_at,t.task_key""",
            (persistence.tenant_id(), normalized),
        )
        rows = cursor.fetchall()
        database.rollback()
    result: list[dict] = []
    for row in rows:
        payload = row[13] or {}
        result.append(
            {
                "task_id": str(row[0]),
                "request_id": row[1],
                "candidate_id": row[2],
                "offer_id": str(row[3]),
                "task_key": row[4],
                "title": row[5],
                "owner_role": row[6],
                "required": bool(row[7]),
                "due_at": row[8].isoformat() if row[8] else None,
                "dependencies": row[9] or [],
                "status": row[10],
                "revision": int(row[11]),
                "warehouse_id": row[12],
                "warehouse_name": payload.get("warehouse_name") or payload.get("warehouseName") or row[12],
                "position_label": payload.get("position_label") or payload.get("positionLabel") or payload.get("position_code") or payload.get("positionCode") or "",
                "candidate_name": next(
                    (
                        item.get("full_name") or item.get("fullName")
                        for item in (payload.get("candidates") or [])
                        if str(item.get("id")) == str(row[2])
                    ),
                    None,
                ),
            }
        )
    return result
