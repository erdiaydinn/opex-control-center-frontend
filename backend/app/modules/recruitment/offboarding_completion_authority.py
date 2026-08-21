"""Production offboarding completion authority.

Recruitment owns checklist governance; Workforce owns employee access.  This
module composes both authorities so an API-level CLOSED state can never be
created before the Employee Master exit projection succeeds.
"""
from __future__ import annotations

from datetime import datetime

from .lifecycle_authority import (
    RecruitmentLifecycleError,
    close_offboarding_case as close_offboarding_case_record,
    offboarding_summary,
)
from .workforce_offboarding_bridge import (
    WorkforceOffboardingBridgeError,
    apply_offboarding_to_workforce,
)


def close_offboarding_with_workforce(case_id: str, *, actor: str) -> dict:
    summary = offboarding_summary(case_id)
    if summary["status"] != "READY_TO_CLOSE":
        raise RecruitmentLifecycleError(
            "Tüm required offboarding task tamamlanmadan case kapatılamaz."
        )
    try:
        effective_at = datetime.fromisoformat(summary["effective_at"])
        workforce = apply_offboarding_to_workforce(
            summary["employee_id"],
            effective_at=effective_at,
            actor=actor,
        )
    except (ValueError, WorkforceOffboardingBridgeError) as error:
        raise RecruitmentLifecycleError(str(error)) from error

    # The Workforce projection intentionally happens before the Recruitment
    # terminal commit.  If the latter loses a concurrency race, a retry is safe:
    # the bridge detects the already-authoritative employment_end and is
    # idempotent instead of emitting duplicate revocation work.
    closed = close_offboarding_case_record(case_id, actor=actor)
    return {
        **closed,
        "workforce_authority": workforce,
        "closure_truth_boundary": "RECRUITMENT_TASKS_PLUS_WORKFORCE_EMPLOYEE_MASTER_AUTHORITY",
    }
