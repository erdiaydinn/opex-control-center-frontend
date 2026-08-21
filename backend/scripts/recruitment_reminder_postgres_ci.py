"""Real PostgreSQL acceptance for the V47 lifecycle reminder planner."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from uuid import uuid4

import psycopg


ADMIN_URL = os.environ["RECRUITMENT_AUTHORITY_ADMIN_URL"]
TENANT = os.getenv("WORKFORCE_TENANT_ID", "eay-ci")


def seed(point: datetime) -> dict:
    request_id = f"REC-REM-{uuid4().hex[:10]}"
    candidate_id = f"CAND-REM-{uuid4().hex[:10]}"
    schedule_id, slot_id, booking_id = uuid4(), uuid4(), uuid4()
    offer_id = uuid4()
    accepted_offer_id = uuid4()
    task_id = uuid4()
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment.interview_schedules(
                 tenant_id,schedule_id,request_id,stage,title,timezone,meeting_mode,duration_minutes,status,created_by
               ) VALUES(%s,%s,%s,'INTERVIEW','CI reminder interview','Europe/Istanbul','REMOTE',30,'OPEN','ci')""",
            (TENANT, schedule_id, request_id),
        )
        cursor.execute(
            """INSERT INTO recruitment.interview_slots(tenant_id,slot_id,schedule_id,starts_at,ends_at,capacity,status)
               VALUES(%s,%s,%s,%s,%s,1,'OPEN')""",
            (TENANT, slot_id, schedule_id, point + timedelta(hours=8), point + timedelta(hours=8, minutes=30)),
        )
        cursor.execute(
            """INSERT INTO recruitment.interview_bookings(
                 tenant_id,booking_id,schedule_id,request_id,candidate_id,slot_id,status,booked_at
               ) VALUES(%s,%s,%s,%s,%s,%s,'BOOKED',%s)""",
            (TENANT, booking_id, schedule_id, request_id, candidate_id, slot_id, point),
        )
        package = json.dumps({"position": "CI reminder role"})
        cursor.execute(
            """INSERT INTO recruitment.offer_packages(
                 tenant_id,offer_id,request_id,candidate_id,version,package_sha256,package,expires_at,created_by
               ) VALUES(%s,%s,%s,%s,1,%s,%s::jsonb,%s,'ci')""",
            (TENANT, offer_id, request_id, candidate_id, hashlib.sha256(package.encode()).digest(), package, point + timedelta(hours=20)),
        )
        cursor.execute(
            """INSERT INTO recruitment.offer_events(
                 tenant_id,event_id,offer_id,request_id,candidate_id,decision,actor_type,actor_ref,occurred_at
               ) VALUES(%s,%s,%s,%s,%s,'ISSUED','HR','ci',%s)""",
            (TENANT, uuid4(), offer_id, request_id, candidate_id, point),
        )
        cursor.execute(
            """INSERT INTO recruitment.onboarding_tasks(
                 tenant_id,task_id,request_id,candidate_id,offer_id,task_key,title,owner_role,required,due_at,status
               ) VALUES(%s,%s,%s,%s,%s,'CI_DUE_TASK','CI due task','HR',true,%s,'PENDING')""",
            (TENANT, task_id, request_id, candidate_id, offer_id, point + timedelta(hours=6)),
        )

        terminal_request = f"{request_id}-T"
        terminal_candidate = f"{candidate_id}-T"
        terminal_package = json.dumps({"position": "CI accepted role"})
        cursor.execute(
            """INSERT INTO recruitment.offer_packages(
                 tenant_id,offer_id,request_id,candidate_id,version,package_sha256,package,expires_at,created_by
               ) VALUES(%s,%s,%s,%s,1,%s,%s::jsonb,%s,'ci')""",
            (TENANT, accepted_offer_id, terminal_request, terminal_candidate,
             hashlib.sha256(terminal_package.encode()).digest(), terminal_package, point + timedelta(hours=12)),
        )
        cursor.execute(
            """INSERT INTO recruitment.offer_events(
                 tenant_id,event_id,offer_id,request_id,candidate_id,decision,actor_type,actor_ref,occurred_at
               ) VALUES(%s,%s,%s,%s,%s,'ISSUED','HR','ci',%s),
                       (%s,%s,%s,%s,%s,'ACCEPTED','CANDIDATE_CAPABILITY','ci-cap',%s)""",
            (TENANT, uuid4(), accepted_offer_id, terminal_request, terminal_candidate, point,
             TENANT, uuid4(), accepted_offer_id, terminal_request, terminal_candidate, point + timedelta(minutes=5)),
        )
        database.commit()
    return {
        "request_id": request_id,
        "candidate_id": candidate_id,
        "booking_id": booking_id,
        "offer_id": offer_id,
        "task_id": task_id,
        "accepted_offer_id": accepted_offer_id,
    }


def main() -> None:
    point = datetime.now(UTC).replace(microsecond=0)
    ids = seed(point)
    from app.modules.recruitment.lifecycle_authority import claim_candidate_communications
    from app.modules.recruitment.lifecycle_reminders import plan_due_reminders

    first = plan_due_reminders(now=point)
    assert first["created"] == {"interview": 1, "offer": 1, "onboarding": 1}, first
    assert first["created_total"] == 3
    assert first["pii_minimized"] is True

    second = plan_due_reminders(now=point)
    assert second["created_total"] == 0, second

    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT message_type,payload,idempotency_key,status
               FROM recruitment.candidate_communication_outbox
               WHERE tenant_id=%s AND request_id=%s
               ORDER BY message_type""",
            (TENANT, ids["request_id"]),
        )
        rows = cursor.fetchall()
        assert len(rows) == 3, rows
        assert {row[0] for row in rows} == {"INTERVIEW_REMINDER", "OFFER_REMINDER", "ONBOARDING_REMINDER"}
        forbidden = {"email", "phone", "tckn", "full_name", "address"}
        for _, payload, key, status in rows:
            assert status == "QUEUED"
            assert forbidden.isdisjoint(set(payload.keys())), payload
            assert key
        cursor.execute(
            """SELECT count(*) FROM recruitment.candidate_communication_outbox
               WHERE tenant_id=%s AND idempotency_key LIKE %s""",
            (TENANT, f"OFFER_REMINDER:{ids['accepted_offer_id']}:%"),
        )
        assert cursor.fetchone()[0] == 0, "accepted offer received expiry reminder"

    claimed = claim_candidate_communications(worker="ci-reminder-delivery", limit=100)
    claimed_ids = {row["request_id"] for row in claimed}
    assert ids["request_id"] in claimed_ids
    assert all(row["recipient_resolution"] == "SECURE_CANDIDATE_PROFILE_LOOKUP_REQUIRED" for row in claimed)
    print("recruitment V47 lifecycle reminder acceptance: GREEN")


if __name__ == "__main__":
    main()
