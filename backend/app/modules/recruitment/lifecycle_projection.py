"""PII-minimized read projections and task authority lookups for Hiring V47."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.workforce import persistence
from .lifecycle_authority import RecruitmentLifecycleError, _ensure_ready, _uuid


_OFFER_STATUSES = {"PENDING", "APPROVED", "REJECTED", "CANCELLED"}
_MESSAGE_STATUSES = {"QUEUED", "CLAIMED", "SENT", "FAILED", "CANCELLED"}


def list_offer_approval_workflows(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    _ensure_ready()
    normalized = str(status or "").strip().upper()
    if normalized and normalized not in _OFFER_STATUSES:
        raise RecruitmentLifecycleError("Offer approval status filtresi geçersiz.")
    if limit < 1 or limit > 500:
        raise RecruitmentLifecycleError("Offer approval limit 1-500 arasında olmalıdır.")
    tenant = persistence.tenant_id()
    params: list[Any] = [tenant]
    where = "w.tenant_id=%s"
    if normalized:
        where += " AND w.status=%s"
        params.append(normalized)
    params.append(limit)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            f"""SELECT w.offer_id,w.request_id,w.candidate_id,w.required_approvals,w.status,
                       w.requested_by,w.requested_at,w.decided_at,w.revision,
                       count(e.approval_id) FILTER (WHERE e.decision='APPROVED') AS approved_count,
                       count(e.approval_id) FILTER (WHERE e.decision='REJECTED') AS rejected_count,
                       p.version,p.expires_at,p.package_sha256
                FROM recruitment.offer_approval_workflows w
                JOIN recruitment.offer_packages p
                  ON p.tenant_id=w.tenant_id AND p.offer_id=w.offer_id
                LEFT JOIN recruitment.offer_approval_events e
                  ON e.tenant_id=w.tenant_id AND e.offer_id=w.offer_id
                WHERE {where}
                GROUP BY w.offer_id,w.request_id,w.candidate_id,w.required_approvals,w.status,
                         w.requested_by,w.requested_at,w.decided_at,w.revision,
                         p.version,p.expires_at,p.package_sha256
                ORDER BY CASE WHEN w.status='PENDING' THEN 0 ELSE 1 END,w.requested_at DESC
                LIMIT %s""",
            tuple(params),
        )
        return [{
            "offer_id": str(row[0]),
            "request_id": row[1],
            "candidate_id": row[2],
            "required_approvals": int(row[3]),
            "status": row[4],
            "requested_by": row[5],
            "requested_at": row[6].isoformat(),
            "decided_at": row[7].isoformat() if row[7] else None,
            "revision": int(row[8]),
            "approval_count": int(row[9]),
            "rejection_count": int(row[10]),
            "version": int(row[11]),
            "expires_at": row[12].isoformat(),
            "package_sha256": bytes(row[13]).hex(),
            "candidate_delivery_allowed": row[4] == "APPROVED",
            "pii_minimized": True,
        } for row in cursor.fetchall()]


def list_communication_outbox(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Operational projection deliberately excludes payload and recipient details."""
    _ensure_ready()
    normalized = str(status or "").strip().upper()
    if normalized and normalized not in _MESSAGE_STATUSES:
        raise RecruitmentLifecycleError("Communication status filtresi geçersiz.")
    if limit < 1 or limit > 500:
        raise RecruitmentLifecycleError("Communication limit 1-500 arasında olmalıdır.")
    tenant = persistence.tenant_id()
    params: list[Any] = [tenant]
    where = "tenant_id=%s"
    if normalized:
        where += " AND status=%s"
        params.append(normalized)
    params.append(limit)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            f"""SELECT message_id,request_id,candidate_id,message_type,channel,locale,template_key,
                       available_at,status,attempts,claimed_at,claimed_by,delivered_at,failure_code,
                       created_at,created_by,revision
                FROM recruitment.candidate_communication_outbox
                WHERE {where}
                ORDER BY CASE WHEN status IN ('FAILED','QUEUED') THEN 0 ELSE 1 END,available_at,created_at DESC
                LIMIT %s""",
            tuple(params),
        )
        return [{
            "message_id": str(row[0]),
            "request_id": row[1],
            "candidate_id": row[2],
            "message_type": row[3],
            "channel": row[4],
            "locale": row[5],
            "template_key": row[6],
            "available_at": row[7].isoformat(),
            "status": row[8],
            "attempts": int(row[9]),
            "claimed_at": row[10].isoformat() if row[10] else None,
            "claimed_by": row[11],
            "delivered_at": row[12].isoformat() if row[12] else None,
            "failure_code": row[13],
            "created_at": row[14].isoformat(),
            "created_by": row[15],
            "revision": int(row[16]),
            "payload_exposed": False,
            "recipient_exposed": False,
        } for row in cursor.fetchall()]


def offboarding_task_authority(task_id: str) -> dict[str, Any]:
    _ensure_ready()
    task_uuid: UUID = _uuid(task_id, "Offboarding task")
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT t.case_id,t.task_key,t.owner_role,t.required,t.status,c.employee_id,c.status
               FROM recruitment.offboarding_tasks t
               JOIN recruitment.offboarding_cases c
                 ON c.tenant_id=t.tenant_id AND c.case_id=t.case_id
               WHERE t.tenant_id=%s AND t.task_id=%s""",
            (tenant, task_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Offboarding task bulunamadı.")
        return {
            "task_id": str(task_uuid),
            "case_id": str(row[0]),
            "task_key": row[1],
            "owner_role": row[2],
            "required": bool(row[3]),
            "task_status": row[4],
            "employee_id": row[5],
            "case_status": row[6],
        }
