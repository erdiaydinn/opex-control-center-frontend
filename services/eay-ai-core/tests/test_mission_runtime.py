from datetime import datetime, timezone

import pytest

from app.mission_runtime import (
    MissionDefinition,
    MissionStatus,
    MissionStep,
    StepStatus,
    new_checkpoint,
    record_step_result,
    resume_plan,
    runnable_steps,
    with_approval,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 1, 0, tzinfo=UTC)


def _mission():
    return MissionDefinition(
        mission_id="carsi-stock-adjustment",
        objective="Adjust one SKU safely and verify the resulting stock",
        tenant_id="warehouse:fulya",
        steps=(
            MissionStep(step_id="read", description="Read current stock"),
            MissionStep(
                step_id="write",
                description="Submit stock adjustment",
                depends_on=("read",),
                side_effect=True,
                idempotency_key="adjustment:fulya:sku-1:3:zayi",
                effect_verifier_ref="capability://inventory.read-stock",
            ),
            MissionStep(
                step_id="verify",
                description="Verify stock state",
                depends_on=("write",),
            ),
        ),
    )


def test_mission_resumes_only_dependency_safe_steps():
    definition = _mission()
    checkpoint = new_checkpoint(definition, now=NOW)
    assert runnable_steps(definition, checkpoint) == ("read",)

    checkpoint = record_step_result(
        definition,
        checkpoint,
        step_id="read",
        succeeded=True,
        evidence_refs=("stock://27",),
        now=NOW,
    )
    assert resume_plan(definition, checkpoint) == ("write",)


def test_ambiguous_write_outcome_halts_instead_of_replaying_side_effect():
    definition = _mission()
    checkpoint = new_checkpoint(definition, now=NOW)
    checkpoint = record_step_result(definition, checkpoint, step_id="read", succeeded=True, now=NOW)
    checkpoint = record_step_result(
        definition,
        checkpoint,
        step_id="write",
        succeeded=False,
        ambiguous_outcome=True,
        error="portal_timeout_after_submit",
        now=NOW,
    )

    assert checkpoint.status is MissionStatus.HALTED
    write_state = {item.step_id: item for item in checkpoint.steps}["write"]
    assert write_state.status is StepStatus.BLOCKED
    assert resume_plan(definition, checkpoint) == ()


def test_retry_budget_is_bounded_for_failed_nonterminal_step():
    definition = MissionDefinition(
        mission_id="research",
        objective="Retry a bounded read",
        tenant_id="tenant:a",
        steps=(MissionStep(step_id="fetch", description="Fetch source", max_attempts=2),),
    )
    checkpoint = new_checkpoint(definition, now=NOW)
    checkpoint = record_step_result(
        definition, checkpoint, step_id="fetch", succeeded=False, error="timeout", now=NOW
    )
    assert checkpoint.status is MissionStatus.RUNNING
    assert resume_plan(definition, checkpoint) == ("fetch",)

    checkpoint = record_step_result(
        definition, checkpoint, step_id="fetch", succeeded=False, error="timeout", now=NOW
    )
    assert checkpoint.status is MissionStatus.FAILED
    assert resume_plan(definition, checkpoint) == ()


def test_irreversible_step_cannot_exist_without_human_approval_contract():
    with pytest.raises(ValueError, match="mission_irreversible_step_requires_human_approval"):
        MissionStep(
            step_id="terminate",
            description="Terminate employee",
            side_effect=True,
            irreversible=True,
            idempotency_key="terminate:1",
            effect_verifier_ref="hr://employee-state",
        )


def test_approval_gated_step_is_not_runnable_until_approval_is_bound():
    definition = MissionDefinition(
        mission_id="approved-write",
        objective="Perform approved irreversible action",
        tenant_id="tenant:a",
        steps=(
            MissionStep(
                step_id="write",
                description="Irreversible write",
                side_effect=True,
                irreversible=True,
                requires_human_approval=True,
                required_permission="hr.terminate",
                idempotency_key="irreversible:1",
                effect_verifier_ref="hr://state",
            ),
        ),
    )
    checkpoint = new_checkpoint(definition, now=NOW)
    assert runnable_steps(definition, checkpoint) == ()

    checkpoint = with_approval(
        definition,
        checkpoint,
        step_id="write",
        approval_ref="approval://director/42",
        now=NOW,
    )
    assert runnable_steps(definition, checkpoint) == ("write",)


def test_dependency_cycles_are_rejected():
    with pytest.raises(ValueError, match="mission_dependency_cycle"):
        MissionDefinition(
            mission_id="cycle",
            objective="invalid",
            tenant_id="tenant:a",
            steps=(
                MissionStep(step_id="a", description="a", depends_on=("b",)),
                MissionStep(step_id="b", description="b", depends_on=("a",)),
            ),
        )
