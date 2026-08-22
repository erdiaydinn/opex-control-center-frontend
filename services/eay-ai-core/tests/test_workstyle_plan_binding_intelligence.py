from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.workstyle_agent_os import (
    WorkActionClass,
    WorkCapability,
    WorkTaskSpec,
    admit_work_plan,
    build_work_approval,
    build_work_plan,
)

NOW = datetime(2026, 8, 21, 6, 55, tzinfo=UTC)


def _mutation_plan(objective: str):
    return build_work_plan(
        tenant_id="tenant-a",
        company_id="company-a",
        session_id="session-a",
        revision=7,
        objective=objective,
        tasks=(
            WorkTaskSpec(
                task_id="mutate",
                objective=objective,
                required_capabilities=(WorkCapability.RPA,),
                action_class=WorkActionClass.EXTERNAL_MUTATION,
            ),
        ),
        created_at=NOW,
    )


def test_approval_cannot_be_reused_for_different_plan_with_same_revision() -> None:
    approved_plan = _mutation_plan("Apply approved configuration A")
    substituted_plan = _mutation_plan("Apply materially different configuration B")
    assert approved_plan.revision == substituted_plan.revision
    assert approved_plan.fingerprint != substituted_plan.fingerprint

    approval = build_work_approval(
        plan=approved_plan,
        task_id="mutate",
        action_class=WorkActionClass.EXTERNAL_MUTATION,
        approved_by="user-a",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )

    with pytest.raises(ValueError, match="work_approval_plan_fingerprint_mismatch"):
        admit_work_plan(
            plan=substituted_plan,
            available_capabilities=(WorkCapability.RPA,),
            mastery_decisions=(),
            approvals=(approval,),
            now=NOW + timedelta(minutes=1),
        )


def test_plan_admission_is_bound_to_exact_plan_fingerprint() -> None:
    plan = build_work_plan(
        tenant_id="tenant-a",
        company_id="company-a",
        session_id="session-read",
        revision=1,
        objective="Read current evidence",
        tasks=(
            WorkTaskSpec(
                task_id="read",
                objective="Read current evidence",
                required_capabilities=(WorkCapability.FILES,),
            ),
        ),
        created_at=NOW,
    )

    admission = admit_work_plan(
        plan=plan,
        available_capabilities=(WorkCapability.FILES,),
        mastery_decisions=(),
        approvals=(),
        now=NOW,
    )

    assert admission.plan_fingerprint == plan.fingerprint
    assert admission.all_tasks_ready is True
    assert admission.execution_authority_granted is False
