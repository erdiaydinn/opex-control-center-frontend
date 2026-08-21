"""Idempotent reminder planner for Hiring V47 communication outbox.

No candidate destination or raw PII is copied into the outbox. The delivery
worker resolves the recipient from the protected candidate profile only after
claiming a message.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4

from app.modules.workforce import persistence
from .lifecycle_authority import RecruitmentLifecycleError, _ensure_ready


_SYSTEM_ACTOR = "SYSTEM_LIFECYCLE_REMINDER_PLANNER"


def _now() -> datetime:
    return datetime.now(UTC)


def _enqueue(cursor, tenant: str, *, request_id: str, candidate_id: str, message_type: str, template_key: str, payload: dict, idempotency_key: str, available_at: datetime) -> int:
    cursor.execute(
        """INSERT INTO recruitment.candidate_communication_outbox(
             tenant_id,message_id,request_id,candidate_id,message_type,channel,locale,template_key,payload,
             idempotency_key,available_at,status,created_by
           ) VALUES(%s,%s,%s,%s,%s,'EMAIL','tr-TR',%s,%s::jsonb,%s,%s,'QUEUED',%s)
           ON CONFLICT (tenant_id,idempotency_key) DO NOTHING""",
        (
            tenant,
            uuid4(),
            request_id,
            candidate_id,
            message_type,
            template_key,
            json.dumps(payload, ensure_ascii=False),
            idempotency_key,
            available_at,
            _SYSTEM_ACTOR,
        ),
    )
    return int(cursor.rowcount or 0)


def plan_due_reminders(*, now: datetime | None = None) -> dict:
    _ensure_ready()
    point = now or _now()
    if point.tzinfo is None:
        raise RecruitmentLifecycleError("Reminder planner now timezone-aware olmalıdır.")
    tenant = persistence.tenant_id()
    created = {"interview": 0, "offer": 0, "onboarding": 0}
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        # Serialize one planner pass per tenant. Idempotency keys are still the hard guarantee.
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"recruitment-reminders:{tenant}",))

        cursor.execute(
            """SELECT b.booking_id,b.request_id,b.candidate_id,b.slot_id,s.starts_at,sch.schedule_id
               FROM recruitment.interview_bookings b
               JOIN recruitment.interview_slots s
                 ON s.tenant_id=b.tenant_id AND s.slot_id=b.slot_id
               JOIN recruitment.interview_schedules sch
                 ON sch.tenant_id=b.tenant_id AND sch.schedule_id=b.schedule_id
               WHERE b.tenant_id=%s AND b.status='BOOKED' AND s.status='OPEN' AND sch.status='OPEN'
                 AND s.starts_at>%s AND s.starts_at<=%s
               ORDER BY s.starts_at""",
            (tenant, point, point + timedelta(hours=24)),
        )
        for booking_id, request_id, candidate_id, slot_id, starts_at, schedule_id in cursor.fetchall():
            created["interview"] += _enqueue(
                cursor,
                tenant,
                request_id=request_id,
                candidate_id=candidate_id,
                message_type="INTERVIEW_REMINDER",
                template_key="interview-reminder-24h-v1",
                payload={"schedule_id": str(schedule_id), "slot_id": str(slot_id), "starts_at": starts_at.isoformat()},
                idempotency_key=f"INTERVIEW_REMINDER:{booking_id}:{starts_at.isoformat()}",
                available_at=point,
            )

        cursor.execute(
            """SELECT p.offer_id,p.request_id,p.candidate_id,p.expires_at
               FROM recruitment.offer_packages p
               WHERE p.tenant_id=%s AND p.expires_at>%s AND p.expires_at<=%s
                 AND EXISTS (
                   SELECT 1 FROM recruitment.offer_events issued
                   WHERE issued.tenant_id=p.tenant_id AND issued.offer_id=p.offer_id AND issued.decision='ISSUED'
                 )
                 AND NOT EXISTS (
                   SELECT 1 FROM recruitment.offer_events terminal
                   WHERE terminal.tenant_id=p.tenant_id AND terminal.offer_id=p.offer_id
                     AND terminal.decision IN ('ACCEPTED','DECLINED','WITHDRAWN','EXPIRED')
                 )
               ORDER BY p.expires_at""",
            (tenant, point, point + timedelta(hours=48)),
        )
        for offer_id, request_id, candidate_id, expires_at in cursor.fetchall():
            created["offer"] += _enqueue(
                cursor,
                tenant,
                request_id=request_id,
                candidate_id=candidate_id,
                message_type="OFFER_REMINDER",
                template_key="offer-expiry-reminder-48h-v1",
                payload={"offer_id": str(offer_id), "expires_at": expires_at.isoformat()},
                idempotency_key=f"OFFER_REMINDER:{offer_id}:{expires_at.isoformat()}",
                available_at=point,
            )

        cursor.execute(
            """SELECT task_id,request_id,candidate_id,task_key,due_at
               FROM recruitment.onboarding_tasks
               WHERE tenant_id=%s AND required=true AND status IN ('PENDING','IN_PROGRESS','BLOCKED')
                 AND due_at IS NOT NULL AND due_at>%s AND due_at<=%s
               ORDER BY due_at""",
            (tenant, point, point + timedelta(hours=24)),
        )
        for task_id, request_id, candidate_id, task_key, due_at in cursor.fetchall():
            created["onboarding"] += _enqueue(
                cursor,
                tenant,
                request_id=request_id,
                candidate_id=candidate_id,
                message_type="ONBOARDING_REMINDER",
                template_key="onboarding-due-reminder-24h-v1",
                payload={"task_id": str(task_id), "task_key": task_key, "due_at": due_at.isoformat()},
                idempotency_key=f"ONBOARDING_REMINDER:{task_id}:{due_at.isoformat()}",
                available_at=point,
            )

        database.commit()
    return {
        "planned_at": point.isoformat(),
        "created": created,
        "created_total": sum(created.values()),
        "pii_minimized": True,
        "delivery_resolution": "SECURE_CANDIDATE_PROFILE_LOOKUP_REQUIRED",
    }
