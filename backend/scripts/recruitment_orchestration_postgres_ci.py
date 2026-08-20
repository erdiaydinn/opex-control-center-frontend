"""Real PostgreSQL acceptance for V44 orchestration and V45 audit fencing."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg


ADMIN_URL = os.environ["RECRUITMENT_AUTHORITY_ADMIN_URL"]
TENANT = os.getenv("WORKFORCE_TENANT_ID", "eay-ci")
BACKEND = Path(__file__).resolve().parents[1]
M44 = BACKEND / "migrations" / "028_recruitment_orchestration.sql"
M45 = BACKEND / "migrations" / "029_workforce_audit_chain_fencing.sql"


def runtime_url() -> str:
    parsed = urlsplit(ADMIN_URL)
    host = parsed.hostname or "localhost"
    host = f"{host}:{parsed.port}" if parsed.port else host
    return urlunsplit((parsed.scheme, f"workforce_runtime:{quote('workforce_runtime_ci')}@{host}", parsed.path, parsed.query, parsed.fragment))


def apply(path: Path) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(path.read_text(encoding="utf-8"))
        database.commit()


def seed_request() -> tuple[str, str]:
    request_id = f"REC-ORCH-{uuid4().hex[:10]}"
    candidate_id = f"CAND-{uuid4().hex[:12]}"
    payload = {
        "id": request_id,
        "status": "SOURCING",
        "warehouse_id": "CI-WH",
        "warehouse_name": "CI Warehouse",
        "position_code": "STORE_STAFF",
        "position_label": "Store Staff",
        "quantity": 1,
        "revision": 1,
        "history": [],
        "candidates": [
            {
                "id": candidate_id,
                "full_name": "CI Candidate",
                "source_ref": f"ci:{candidate_id}",
                "status": "APPROVED",
                "evidence": [],
            }
        ],
    }
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_requests(
                 tenant_id,id,status,warehouse_id,revision,created_at,payload
               ) VALUES(%s,%s,'SOURCING','CI-WH',1,now(),%s::jsonb)""",
            (TENANT, request_id, json.dumps(payload)),
        )
        database.commit()
    return request_id, candidate_id


def end_to_end_orchestration() -> None:
    from app.modules.recruitment import orchestration

    request_id, candidate_id = seed_request()
    template = orchestration.create_pipeline_template(
        template_key=f"STORE_STAFF_{uuid4().hex[:6]}",
        name="CI Store Staff Governed Pipeline",
        stages=[
            {"key": "SOURCING", "label": "Sourcing", "sla_hours": 24},
            {"key": "INTERVIEW", "label": "Structured Interview", "sla_hours": 24, "min_scorecards": 2, "min_average_score": 75},
            {"key": "OFFER", "label": "Offer", "sla_hours": 24},
            {"key": "PREBOARDING", "label": "Preboarding", "sla_hours": 72},
            {"key": "READY_TO_HIRE", "label": "Ready to Hire", "sla_hours": 24},
        ],
        actor="ci-hr",
    )
    orchestration.assign_pipeline(request_id, candidate_id, template["template_id"], "ci-hr")
    orchestration.transition_stage(request_id, candidate_id, "INTERVIEW", "screen passed", "ci-hr")

    # One scorecard is deliberately insufficient.
    orchestration.submit_scorecard(
        request_id,
        candidate_id,
        competencies={"operations": 90, "safety": 85},
        recommendation="STRONG_HIRE",
        conflict_declared=False,
        interviewer_id="ci-interviewer-1",
    )
    try:
        orchestration.transition_stage(request_id, candidate_id, "OFFER", "", "ci-hr")
    except orchestration.RecruitmentOrchestrationError:
        pass
    else:
        raise AssertionError("pipeline advanced without required independent scorecards")

    orchestration.submit_scorecard(
        request_id,
        candidate_id,
        competencies={"operations": 80, "safety": 82},
        recommendation="HIRE",
        conflict_declared=False,
        interviewer_id="ci-interviewer-2",
    )
    orchestration.transition_stage(request_id, candidate_id, "OFFER", "interview gate passed", "ci-hr")
    offer = orchestration.create_offer(
        request_id,
        candidate_id,
        package={
            "country_code": "TR",
            "locale": "tr-TR",
            "position": "Store Staff",
            "employment_type": "FULL_TIME",
            "work_location": "CI Warehouse",
            "employment_start": (datetime.now(UTC).date() + timedelta(days=7)).isoformat(),
            "currency": "TRY",
            "compensation_amount": 50000,
            "compensation_period": "MONTHLY_GROSS",
            "agreement_template_key": "TR_STORE_STAFF_V1",
        },
        expires_in_hours=168,
        actor="ci-hr",
    )
    capability = orchestration.issue_offer_decision_capability(
        offer["offer_id"], expires_in_hours=72, actor="ci-hr"
    )
    viewed = orchestration.get_offer_by_capability(capability["capability"])
    assert viewed["offer_id"] == offer["offer_id"]
    assert viewed["decision_available"] is True

    def decide() -> tuple[bool, str]:
        try:
            result = orchestration.decide_offer_with_capability(capability["capability"], "ACCEPTED")
            return True, result["decision"]
        except orchestration.RecruitmentOrchestrationError as error:
            return False, str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(lambda _: decide(), range(2)))
    assert sum(ok for ok, _ in decisions) == 1, decisions

    orchestration.transition_stage(request_id, candidate_id, "PREBOARDING", "offer accepted", "ci-hr")
    summary = orchestration.candidate_orchestration_summary(request_id, candidate_id)
    tasks = {task["task_key"]: task for task in summary["onboarding_tasks"]}
    expected_tasks = {"HR_EMPLOYMENT_PACKET", "IT_IDENTITY_ACCOUNT", "ADMIN_ASSET_UNIFORM", "ACADEMY_MANDATORY_LEARNING", "OPS_FIRST_SHIFT_READY"}
    assert expected_tasks == set(tasks), tasks

    def complete(key: str) -> None:
        orchestration.update_onboarding_task(tasks[key]["task_id"], status="COMPLETED", note=f"ci complete {key}", actor=f"ci-{tasks[key]['owner_role'].lower()}")

    complete("HR_EMPLOYMENT_PACKET")
    complete("IT_IDENTITY_ACCOUNT")
    complete("ADMIN_ASSET_UNIFORM")
    complete("ACADEMY_MANDATORY_LEARNING")
    complete("OPS_FIRST_SHIFT_READY")
    orchestration.transition_stage(request_id, candidate_id, "READY_TO_HIRE", "all required preboarding complete", "ci-hr")
    readiness = orchestration.require_hire_ready(request_id, candidate_id)
    assert readiness["ready"] is True
    assert readiness["pipeline_stage"] == "READY_TO_HIRE"

    note = orchestration.append_candidate_note(
        request_id, candidate_id, note_type="FOLLOW_UP", visibility="RECRUITMENT_TEAM", body="CI immutable note", actor="ci-hr"
    )
    assert note["immutable"] is True
    analytics = orchestration.funnel_analytics()
    assert any(row["stage"] == "READY_TO_HIRE" for row in analytics["pipeline_stages"])


def rls_and_immutability() -> None:
    other_template_id = uuid4()
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment.pipeline_templates(
                 tenant_id,template_id,template_key,version,name,stages,created_by
               ) VALUES('other-tenant',%s,'OTHER',1,'Other','[{"key":"A"},{"key":"READY_TO_HIRE"}]'::jsonb,'ci')""",
            (other_template_id,),
        )
        database.commit()
    with psycopg.connect(runtime_url(), autocommit=False) as database, database.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM recruitment.pipeline_templates WHERE template_id=%s", (other_template_id,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT offer_id FROM recruitment.offer_packages WHERE tenant_id=%s LIMIT 1", (TENANT,))
        row = cursor.fetchone()
        assert row is not None
        try:
            cursor.execute("UPDATE recruitment.offer_packages SET version=version+1 WHERE tenant_id=%s AND offer_id=%s", (TENANT, row[0]))
        except psycopg.Error:
            database.rollback()
        else:
            raise AssertionError("immutable offer package was updateable")


def audit_fork_is_rejected() -> None:
    with psycopg.connect(runtime_url(), autocommit=False) as database, database.cursor() as cursor:
        cursor.execute("SELECT hash FROM workforce_audit WHERE tenant_id=%s ORDER BY sequence DESC LIMIT 1", (TENANT,))
        row = cursor.fetchone()
        previous = row[0] if row else "GENESIS"

    barrier_time = datetime.now(UTC)
    def attempt(index: int):
        audit_hash = sha256(f"ci-fork-{index}-{uuid4()}".encode()).hexdigest()
        record = {
            "id": f"AUD-CI-FORK-{uuid4().hex}",
            "tenant_id": TENANT,
            "at": barrier_time.isoformat(),
            "event": "CI_AUDIT_FORK_PROBE",
            "actor": f"ci-{index}",
            "previous_hash": previous,
            "hash": audit_hash,
        }
        try:
            with psycopg.connect(runtime_url(), autocommit=False) as database, database.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO workforce_audit(tenant_id,id,at,event,actor,record,previous_hash,hash)
                       VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (TENANT, record["id"], barrier_time, record["event"], record["actor"], json.dumps(record), previous, audit_hash),
                )
                database.commit()
                return True, None
        except psycopg.Error as error:
            return False, error.sqlstate

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(ok for ok, _ in results) == 1, results
    failures = [state for ok, state in results if not ok]
    assert failures == ["40001"], results


def replay() -> None:
    apply(M44)
    apply(M45)
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0]) >= 45
        cursor.execute(
            """SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class
               WHERE oid=ANY(ARRAY[
                 'recruitment.pipeline_templates'::regclass,
                 'recruitment.pipeline_assignments'::regclass,
                 'recruitment.interview_scorecards'::regclass,
                 'recruitment.offer_packages'::regclass,
                 'recruitment.offer_decision_capabilities'::regclass,
                 'recruitment.onboarding_tasks'::regclass
               ]::oid[])"""
        )
        rows = cursor.fetchall()
        assert len(rows) == 6 and all(rls and force for _, rls, force in rows), rows


def main() -> None:
    apply(M44)
    apply(M45)
    end_to_end_orchestration()
    rls_and_immutability()
    audit_fork_is_rejected()
    replay()
    print("recruitment V44 orchestration and V45 audit fencing acceptance: GREEN")


if __name__ == "__main__":
    main()
