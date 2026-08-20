"""Real PostgreSQL V46 interview capacity, capability rotation and RLS acceptance."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg


ADMIN_URL = os.environ["RECRUITMENT_AUTHORITY_ADMIN_URL"]
TENANT = os.getenv("WORKFORCE_TENANT_ID", "eay-ci")
BACKEND = Path(__file__).resolve().parents[1]
M46 = BACKEND / "migrations" / "030_recruitment_interview_scheduling.sql"


def runtime_url() -> str:
    parsed = urlsplit(ADMIN_URL)
    host = parsed.hostname or "localhost"
    host = f"{host}:{parsed.port}" if parsed.port else host
    return urlunsplit((parsed.scheme, f"workforce_runtime:{quote('workforce_runtime_ci')}@{host}", parsed.path, parsed.query, parsed.fragment))


def seed_request() -> tuple[str, str, str]:
    request_id = f"REC-INT-{uuid4().hex[:10]}"
    candidate_a = f"CAND-A-{uuid4().hex[:10]}"
    candidate_b = f"CAND-B-{uuid4().hex[:10]}"
    candidates = [
        {"id": candidate_a, "full_name": "CI Candidate A", "source_ref": f"ci:{candidate_a}", "status": "APPROVED", "evidence": []},
        {"id": candidate_b, "full_name": "CI Candidate B", "source_ref": f"ci:{candidate_b}", "status": "APPROVED", "evidence": []},
    ]
    payload = {
        "id": request_id,
        "status": "SOURCING",
        "warehouse_id": "CI-WH",
        "warehouse_name": "CI Warehouse",
        "position_code": "STORE_STAFF",
        "position_label": "Store Staff",
        "quantity": 2,
        "revision": 1,
        "history": [],
        "candidates": candidates,
    }
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_requests(
                 tenant_id,id,status,warehouse_id,revision,created_at,payload
               ) VALUES(%s,%s,'SOURCING','CI-WH',1,now(),%s::jsonb)""",
            (TENANT, request_id, json.dumps(payload)),
        )
        database.commit()
    return request_id, candidate_a, candidate_b


def shared_capacity_and_rotation() -> None:
    from app.modules.recruitment import interview_scheduling, orchestration

    request_id, candidate_a, candidate_b = seed_request()
    template = orchestration.create_pipeline_template(
        template_key=f"INTERVIEW_CI_{uuid4().hex[:6]}",
        name="CI Shared Interview Pipeline",
        stages=[
            {"key": "SOURCING", "label": "Sourcing", "sla_hours": 24},
            {"key": "INTERVIEW", "label": "Interview", "sla_hours": 24},
            {"key": "OFFER", "label": "Offer", "sla_hours": 24},
            {"key": "READY_TO_HIRE", "label": "Ready", "sla_hours": 24},
        ],
        actor="ci-hr",
    )
    for candidate_id in (candidate_a, candidate_b):
        orchestration.assign_pipeline(request_id, candidate_id, template["template_id"], "ci-hr")
        orchestration.transition_stage(request_id, candidate_id, "INTERVIEW", "screen passed", "ci-hr")

    starts = datetime.now(UTC) + timedelta(days=2)
    schedule = interview_scheduling.create_schedule(
        request_id,
        candidate_a,
        title="CI shared structured interview",
        timezone="Europe/Istanbul",
        meeting_mode="REMOTE",
        location_label="EAY Meet",
        instructions="Join five minutes early.",
        duration_minutes=45,
        slots=[{"starts_at": starts, "ends_at": starts + timedelta(minutes=45), "capacity": 1}],
        actor="ci-hr",
    )
    assert schedule["capacity_scope"] == "VACANCY_STAGE_SHARED"
    slot_id = schedule["slots"][0]["slot_id"]
    cap_a = interview_scheduling.issue_booking_capability(schedule["schedule_id"], candidate_a, expires_in_hours=24, actor="ci-hr")
    cap_b = interview_scheduling.issue_booking_capability(schedule["schedule_id"], candidate_b, expires_in_hours=24, actor="ci-hr")

    def book(raw_token: str):
        try:
            return True, interview_scheduling.mutate_candidate_booking(raw_token, "BOOK", slot_id)
        except interview_scheduling.InterviewSchedulingError as error:
            return False, str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(book, [cap_a["capability"], cap_b["capability"]]))
    assert sum(ok for ok, _ in results) == 1, results
    winner_index = 0 if results[0][0] else 1
    loser_index = 1 - winner_index
    winner_initial = (cap_a, cap_b)[winner_index]
    loser_initial = (cap_a, cap_b)[loser_index]
    winner_result = results[winner_index][1]

    # Successful mutation rotates the token. The old copied link is a replay.
    try:
        interview_scheduling.mutate_candidate_booking(winner_initial["capability"], "CANCEL")
    except interview_scheduling.InterviewSchedulingError:
        pass
    else:
        raise AssertionError("revoked interview capability replay was accepted")

    cancel = interview_scheduling.mutate_candidate_booking(winner_result["next_capability"], "CANCEL")
    assert cancel["event"] == "CANCELLED"
    assert cancel["next_capability_generation"] == 3

    # The losing transaction rolled back without consuming its capability. Once
    # the winner releases capacity, the second candidate can book the same slot.
    loser_result = interview_scheduling.mutate_candidate_booking(loser_initial["capability"], "BOOK", slot_id)
    assert loser_result["event"] == "BOOKED"
    snapshot = loser_result["schedule"]
    chosen = next(row for row in snapshot["slots"] if row["slot_id"] == slot_id)
    assert chosen["remaining"] == 0

    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute(
            """SELECT event_type,count(*) FROM recruitment.interview_booking_events
               WHERE tenant_id=%s AND schedule_id=%s GROUP BY event_type""",
            (TENANT, schedule["schedule_id"]),
        )
        event_counts = dict(cursor.fetchall())
        assert event_counts.get("BOOKED") == 2 and event_counts.get("CANCELLED") == 1, event_counts
        cursor.execute(
            """SELECT candidate_id,count(*) FROM recruitment.interview_booking_capabilities
               WHERE tenant_id=%s AND schedule_id=%s AND revoked_at IS NULL GROUP BY candidate_id""",
            (TENANT, schedule["schedule_id"]),
        )
        active = dict(cursor.fetchall())
        assert active.get(candidate_a) == 1 and active.get(candidate_b) == 1, active

        event_id = cursor.execute(
            "SELECT event_id FROM recruitment.interview_booking_events WHERE tenant_id=%s AND schedule_id=%s LIMIT 1",
            (TENANT, schedule["schedule_id"]),
        ).fetchone()[0]
        try:
            cursor.execute(
                "UPDATE recruitment.interview_booking_events SET metadata='{}'::jsonb WHERE tenant_id=%s AND event_id=%s",
                (TENANT, event_id),
            )
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("append-only interview booking event was mutable")


def rls_and_replay() -> None:
    other_schedule = uuid4()
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment.interview_schedules(
                 tenant_id,schedule_id,request_id,stage,title,timezone,meeting_mode,duration_minutes,created_by
               ) VALUES('other-tenant',%s,'OTHER-REQUEST','INTERVIEW','Other tenant','UTC','REMOTE',30,'ci')""",
            (other_schedule,),
        )
        database.commit()
    with psycopg.connect(runtime_url(), autocommit=False) as database, database.cursor() as cursor:
        cursor.execute("SELECT set_config('app.workforce_tenant','other-tenant',true)")
        cursor.execute("SELECT count(*) FROM recruitment.interview_schedules WHERE schedule_id=%s", (other_schedule,))
        assert cursor.fetchone()[0] == 0
        database.rollback()

    # Migration is replay-safe and every V46 authority table remains FORCE RLS.
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(M46.read_text(encoding="utf-8"))
        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0] or 0) >= 46
        cursor.execute(
            """SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class
               WHERE oid=ANY(ARRAY[
                 'recruitment.interview_schedules'::regclass,
                 'recruitment.interview_slots'::regclass,
                 'recruitment.interview_bookings'::regclass,
                 'recruitment.interview_booking_capabilities'::regclass,
                 'recruitment.interview_booking_events'::regclass
               ]::oid[])"""
        )
        rows = cursor.fetchall()
        assert len(rows) == 5 and all(rls and force for _, rls, force in rows), rows
        database.commit()


def main() -> None:
    shared_capacity_and_rotation()
    rls_and_replay()
    print("recruitment V46 shared interview capacity rotation RLS acceptance: GREEN")


if __name__ == "__main__":
    main()
