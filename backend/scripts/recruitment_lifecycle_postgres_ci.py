"""Real PostgreSQL acceptance for Hiring V47 lifecycle authority."""
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
M47 = BACKEND / "migrations" / "031_recruitment_lifecycle_authority.sql"


def runtime_url() -> str:
    parsed = urlsplit(ADMIN_URL)
    host = parsed.hostname or "localhost"
    host = f"{host}:{parsed.port}" if parsed.port else host
    return urlunsplit((parsed.scheme, f"workforce_runtime:{quote('workforce_runtime_ci')}@{host}", parsed.path, parsed.query, parsed.fragment))


def apply() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(M47.read_text(encoding="utf-8"))
        database.commit()


def seed_request() -> tuple[str, str]:
    request_id = f"REC-LIFE-{uuid4().hex[:10]}"
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
        "candidates": [{
            "id": candidate_id,
            "full_name": "CI Lifecycle Candidate",
            "source_ref": f"ci:{candidate_id}",
            "status": "APPROVED",
            "evidence": [],
        }],
    }
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_requests(tenant_id,id,status,warehouse_id,revision,created_at,payload)
               VALUES(%s,%s,'SOURCING','CI-WH',1,now(),%s::jsonb)""",
            (TENANT, request_id, json.dumps(payload)),
        )
        database.commit()
    return request_id, candidate_id


def offer_approval_and_capability() -> tuple[str, str, str]:
    from app.modules.recruitment import lifecycle_authority, orchestration

    request_id, candidate_id = seed_request()
    template = orchestration.create_pipeline_template(
        template_key=f"LIFE_{uuid4().hex[:8]}",
        name="CI Lifecycle Offer Pipeline",
        stages=[
            {"key": "OFFER", "label": "Offer", "sla_hours": 24},
            {"key": "READY_TO_HIRE", "label": "Ready", "sla_hours": 24},
        ],
        actor="ci-creator",
    )
    orchestration.assign_pipeline(request_id, candidate_id, template["template_id"], "ci-creator")
    offer = lifecycle_authority.create_offer_for_approval(
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
        actor="ci-creator",
    )
    assert offer["approval_status"] == "PENDING"
    try:
        lifecycle_authority.issue_approved_offer_capability(offer["offer_id"], expires_in_hours=72, actor="ci-creator")
    except lifecycle_authority.RecruitmentLifecycleError:
        pass
    else:
        raise AssertionError("candidate capability issued before approval quorum")
    try:
        lifecycle_authority.decide_offer_approval(offer["offer_id"], decision="APPROVED", reason="self", actor="ci-creator")
    except lifecycle_authority.RecruitmentLifecycleError:
        pass
    else:
        raise AssertionError("offer creator self-approved")

    first = lifecycle_authority.decide_offer_approval(
        offer["offer_id"], decision="APPROVED", reason="finance check", actor="ci-approver-1"
    )
    assert first["approval_status"] == "PENDING" and first["approval_count"] == 1
    try:
        lifecycle_authority.decide_offer_approval(
            offer["offer_id"], decision="APPROVED", reason="duplicate", actor="ci-approver-1"
        )
    except lifecycle_authority.RecruitmentLifecycleError:
        pass
    else:
        raise AssertionError("same approver counted twice")

    def approve(actor: str) -> tuple[bool, str]:
        try:
            result = lifecycle_authority.decide_offer_approval(
                offer["offer_id"], decision="APPROVED", reason="independent approval", actor=actor
            )
            return True, result["approval_status"]
        except lifecycle_authority.RecruitmentLifecycleError as error:
            return False, str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, ["ci-approver-2", "ci-approver-3"]))
    assert sum(ok for ok, _ in results) == 1, results
    summary = lifecycle_authority.offer_approval_summary(offer["offer_id"])
    assert summary["status"] == "APPROVED"
    assert len([event for event in summary["approvals"] if event["decision"] == "APPROVED"]) == 2
    capability = lifecycle_authority.issue_approved_offer_capability(
        offer["offer_id"], expires_in_hours=72, actor="ci-creator"
    )
    assert capability["approval_status"] == "APPROVED"
    assert capability["approval_count"] == 2
    return request_id, candidate_id, offer["offer_id"]


def communication_and_talent_pool(request_id: str, candidate_id: str) -> None:
    from app.modules.recruitment import lifecycle_authority

    try:
        lifecycle_authority.queue_candidate_communication(
            request_id,
            candidate_id,
            message_type="OFFER_REMINDER",
            channel="EMAIL",
            locale="tr-TR",
            template_key="offer-reminder-v1",
            payload={"email": "candidate@example.com"},
            idempotency_key=f"pii-{uuid4()}",
            available_at=None,
            actor="ci-hr",
        )
    except lifecycle_authority.RecruitmentLifecycleError:
        pass
    else:
        raise AssertionError("raw PII entered communication outbox")

    key = f"offer-reminder:{uuid4()}"
    queued = lifecycle_authority.queue_candidate_communication(
        request_id,
        candidate_id,
        message_type="OFFER_REMINDER",
        channel="EMAIL",
        locale="tr-TR",
        template_key="offer-reminder-v1",
        payload={"offer_id": "opaque-offer-ref", "stage": "OFFER"},
        idempotency_key=key,
        available_at=None,
        actor="ci-hr",
    )
    replay = lifecycle_authority.queue_candidate_communication(
        request_id,
        candidate_id,
        message_type="OFFER_REMINDER",
        channel="EMAIL",
        locale="tr-TR",
        template_key="offer-reminder-v1",
        payload={"offer_id": "opaque-offer-ref", "stage": "OFFER"},
        idempotency_key=key,
        available_at=None,
        actor="ci-hr",
    )
    assert replay["message_id"] == queued["message_id"] and replay["idempotent_replay"] is True
    claimed = lifecycle_authority.claim_candidate_communications(worker="ci-delivery", limit=10)
    item = next(row for row in claimed if row["message_id"] == queued["message_id"])
    assert item["recipient_resolution"] == "SECURE_CANDIDATE_PROFILE_LOOKUP_REQUIRED"
    failed = lifecycle_authority.settle_candidate_communication(
        queued["message_id"], delivered=False, failure_code="TEMPORARY_PROVIDER_ERROR", worker="ci-delivery"
    )
    assert failed["status"] == "FAILED"
    claimed_again = lifecycle_authority.claim_candidate_communications(worker="ci-delivery", limit=10)
    assert any(row["message_id"] == queued["message_id"] for row in claimed_again)
    sent = lifecycle_authority.settle_candidate_communication(
        queued["message_id"], delivered=True, failure_code="", worker="ci-delivery"
    )
    assert sent["status"] == "SENT"

    membership = lifecycle_authority.add_to_talent_pool(
        request_id,
        candidate_id,
        pool_key="STORE_STAFF_TR",
        tags=["ISTANBUL", "DARKSTORE"],
        consent_basis="EXPLICIT_CANDIDATE_CONSENT",
        consent_record_ref=f"CONSENT-{uuid4().hex}",
        consent_days=365,
        actor="ci-hr",
    )
    assert membership["status"] == "ACTIVE"
    rows = lifecycle_authority.list_talent_pool("STORE_STAFF_TR")
    assert any(row["membership_id"] == membership["membership_id"] for row in rows)
    withdrawn = lifecycle_authority.withdraw_talent_pool_membership(membership["membership_id"], actor="ci-hr")
    assert withdrawn["status"] == "WITHDRAWN"


def offboarding() -> str:
    from app.modules.recruitment import lifecycle_authority

    case = lifecycle_authority.create_offboarding_case(
        f"EMP-{uuid4().hex[:10]}",
        effective_at=datetime.now(UTC) + timedelta(days=1),
        reason_code="RESIGNATION",
        note="CI governed exit",
        actor="ci-hr",
    )
    assert case["status"] == "OPEN" and case["close_allowed"] is False
    tasks = {task["task_key"]: task for task in case["tasks"]}
    assert set(tasks) == {
        "HR_EXIT_RECORD", "IT_REVOKE_ACCESS", "ADMIN_RETURN_ASSETS",
        "PAYROLL_FINAL_SETTLEMENT", "ACADEMY_CLOSE_LEARNING", "OPS_REMOVE_ROSTER",
    }
    try:
        lifecycle_authority.close_offboarding_case(case["case_id"], actor="ci-hr")
    except lifecycle_authority.RecruitmentLifecycleError:
        pass
    else:
        raise AssertionError("offboarding closed before tasks")
    try:
        lifecycle_authority.update_offboarding_task(
            tasks["IT_REVOKE_ACCESS"]["task_id"], status="COMPLETED", note="too early", actor="ci-it"
        )
    except lifecycle_authority.RecruitmentLifecycleError:
        pass
    else:
        raise AssertionError("dependent offboarding task completed before HR root")

    case = lifecycle_authority.update_offboarding_task(
        tasks["HR_EXIT_RECORD"]["task_id"], status="COMPLETED", note="hr complete", actor="ci-hr"
    )
    tasks = {task["task_key"]: task for task in case["tasks"]}
    for key, actor in (
        ("IT_REVOKE_ACCESS", "ci-it"),
        ("ADMIN_RETURN_ASSETS", "ci-admin"),
        ("PAYROLL_FINAL_SETTLEMENT", "ci-payroll"),
        ("ACADEMY_CLOSE_LEARNING", "ci-academy"),
        ("OPS_REMOVE_ROSTER", "ci-ops"),
    ):
        case = lifecycle_authority.update_offboarding_task(
            tasks[key]["task_id"], status="COMPLETED", note=f"{key} complete", actor=actor
        )
    assert case["status"] == "READY_TO_CLOSE" and case["close_allowed"] is True
    closed = lifecycle_authority.close_offboarding_case(case["case_id"], actor="ci-hr-closer")
    assert closed["status"] == "CLOSED"
    return case["case_id"]


def rls_and_immutability(offer_id: str, case_id: str) -> None:
    other_membership = uuid4()
    with psycopg.connect(ADMIN_URL, autocommit=False) as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment.talent_pool_memberships(
                 tenant_id,membership_id,subject_key,source_request_id,source_candidate_id,pool_key,tags,
                 consent_basis,consent_record_ref,consent_expires_at,status,created_by
               ) VALUES('other-tenant',%s,%s,'OTHER-REQ','OTHER-CAND','OTHER','[]'::jsonb,
                        'EXPLICIT_CANDIDATE_CONSENT','OTHER-CONSENT',now()+interval '1 day','ACTIVE','ci')""",
            (other_membership, uuid4()),
        )
        database.commit()
    with psycopg.connect(runtime_url(), autocommit=False) as database, database.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM recruitment.talent_pool_memberships WHERE membership_id=%s", (other_membership,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT approval_id FROM recruitment.offer_approval_events WHERE tenant_id=%s AND offer_id=%s LIMIT 1", (TENANT, offer_id))
        approval = cursor.fetchone()
        assert approval is not None
        try:
            cursor.execute("UPDATE recruitment.offer_approval_events SET reason='tamper' WHERE tenant_id=%s AND approval_id=%s", (TENANT, approval[0]))
        except psycopg.Error as error:
            # 42501 means the least-privilege runtime role has no UPDATE grant;
            # 55000 means a more privileged caller reached the append-only trigger.
            # Either is an authoritative mutation denial and neither widens grants.
            assert error.sqlstate in {"42501", "55000"}, error.sqlstate
            database.rollback()
        else:
            raise AssertionError("offer approval event was mutable")
        try:
            cursor.execute("UPDATE recruitment.offboarding_events SET actor_ref='tamper' WHERE tenant_id=%s AND case_id=%s", (TENANT, case_id))
        except psycopg.Error as error:
            assert error.sqlstate in {"42501", "55000"}, error.sqlstate
            database.rollback()
        else:
            raise AssertionError("offboarding event was mutable")


def replay_and_shape() -> None:
    apply()
    tables = [
        "offer_approval_workflows", "offer_approval_events", "candidate_communication_outbox",
        "talent_pool_memberships", "offboarding_cases", "offboarding_tasks", "offboarding_events",
    ]
    with psycopg.connect(ADMIN_URL) as database, database.cursor() as cursor:
        cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
        assert int(cursor.fetchone()[0]) >= 47
        for table in tables:
            cursor.execute(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",
                (f"recruitment.{table}",),
            )
            row = cursor.fetchone()
            assert row == (True, True), (table, row)


def main() -> None:
    apply()
    request_id, candidate_id, offer_id = offer_approval_and_capability()
    communication_and_talent_pool(request_id, candidate_id)
    case_id = offboarding()
    rls_and_immutability(offer_id, case_id)
    replay_and_shape()
    print("recruitment V47 lifecycle authority acceptance: GREEN")


if __name__ == "__main__":
    main()
