"""Real PostgreSQL acceptance for Recruitment -> Workforce offboarding closure."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.modules.recruitment import lifecycle_authority
from app.modules.recruitment.offboarding_completion_authority import close_offboarding_with_workforce
from app.modules.workforce import persistence, service as workforce


ISTANBUL = ZoneInfo("Europe/Istanbul")


def seed_employee_with_future_shift() -> tuple[str, str, str]:
    workforce.initialize_workforce()
    employee_id = f"EMP-OFF-{uuid4().hex[:10]}"
    tckn = f"9{int(uuid4().hex[:10], 16) % 10_000_000_000:010d}"
    warehouse = workforce.list_warehouses()[0]
    today = datetime.now(ISTANBUL).date()
    result = workforce.upsert_people(
        [{
            "employee_id": employee_id,
            "tckn": tckn,
            "full_name": "CI Offboarding Employee",
            "warehouse_id": warehouse["id"],
            "active": True,
            "employment_start": (today - timedelta(days=30)).isoformat(),
            "employment_end": None,
        }],
        "ci-offboarding-seed",
    )
    assert result["created"] == 1, result
    shift = workforce.create_shift(
        {
            "person_id": employee_id,
            "person_name": "CI Offboarding Employee",
            "warehouse_id": warehouse["id"],
            "date": (today + timedelta(days=1)).isoformat(),
            "start": "09:00",
            "end": "18:00",
            "break_minutes": 60,
            "role": "Picker",
        },
        "ci-offboarding-seed",
    )
    assert shift["status"] == "Atandı"
    return employee_id, shift["id"], today.isoformat()


def complete_case(employee_id: str) -> dict:
    case = lifecycle_authority.create_offboarding_case(
        employee_id,
        effective_at=datetime.now(UTC),
        reason_code="RESIGNATION",
        note="CI Workforce-bound exit",
        actor="ci-hr",
    )
    tasks = {task["task_key"]: task for task in case["tasks"]}
    case = lifecycle_authority.update_offboarding_task(
        tasks["HR_EXIT_RECORD"]["task_id"], status="COMPLETED", note="hr packet complete", actor="ci-hr"
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
    assert case["status"] == "READY_TO_CLOSE", case
    return case


def assert_persisted(employee_id: str, shift_id: str, employment_end: str) -> None:
    # Re-read the authoritative PostgreSQL snapshot, not only process memory.
    people = persistence.load_collection("people")
    shifts = persistence.load_collection("shifts")
    person = next(row for row in people if str(row.get("employee_id")) == employee_id)
    shift = next(row for row in shifts if str(row.get("id")) == shift_id)
    assert person["employment_end"] == employment_end, person
    assert person["active"] is False, person
    assert shift["status"] == "İptal", shift
    assert shift["cancel_reason"] == "EMPLOYMENT_ENDED", shift

    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT count(*) FROM workforce_identity_revocation_outbox
               WHERE tenant_id=%s AND employee_id=%s AND status='PENDING'""",
            (persistence.tenant_id(), employee_id),
        )
        assert int(cursor.fetchone()[0]) == 1
        cursor.execute(
            """SELECT count(*) FROM workforce_audit
               WHERE tenant_id=%s AND event='EMPLOYMENT_LIFECYCLE_IMPORTED'
                 AND record->>'file_name'='recruitment-offboarding-authority'""",
            (persistence.tenant_id(),),
        )
        assert int(cursor.fetchone()[0]) >= 1


def main() -> None:
    employee_id, shift_id, employment_end = seed_employee_with_future_shift()
    case = complete_case(employee_id)
    closed = close_offboarding_with_workforce(case["case_id"], actor="ci-hr-closer")
    assert closed["status"] == "CLOSED", closed
    assert closed["closure_truth_boundary"] == "RECRUITMENT_TASKS_PLUS_WORKFORCE_EMPLOYEE_MASTER_AUTHORITY"
    authority = closed["workforce_authority"]
    assert authority["access_state"] == "DEACTIVATED", authority
    assert authority["workforce_access_allowed"] is False, authority
    assert authority["active_future_shifts"] == 0, authority
    assert authority["cancelled_shifts"] == 1, authority
    assert authority["identity_revocations_queued"] == 1, authority

    person = workforce.resolve_person_identity(employee_id, "EMPLOYEE_ID")
    assert person is not None and person["active"] is False
    assert workforce.person_has_workforce_access(person) is False
    shift = next(row for row in workforce.list_shifts(employee_id) if row["id"] == shift_id)
    assert shift["status"] == "İptal" and shift["cancel_reason"] == "EMPLOYMENT_ENDED"
    assert_persisted(employee_id, shift_id, employment_end)

    # A production retry after the Workforce commit must not emit another
    # identity revocation. The terminal Recruitment row itself rejects a second
    # close, while the bridge stays idempotent if invoked independently.
    from app.modules.recruitment.workforce_offboarding_bridge import apply_offboarding_to_workforce
    replay = apply_offboarding_to_workforce(
        employee_id, effective_at=datetime.now(UTC), actor="ci-retry"
    )
    assert replay["idempotent_replay"] is True, replay
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT count(*) FROM workforce_identity_revocation_outbox WHERE tenant_id=%s AND employee_id=%s",
            (persistence.tenant_id(), employee_id),
        )
        assert int(cursor.fetchone()[0]) == 1

    print("recruitment Workforce-bound offboarding closure acceptance: GREEN")


if __name__ == "__main__":
    main()
