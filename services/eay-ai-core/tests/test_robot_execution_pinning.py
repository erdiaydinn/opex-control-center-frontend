from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.mission_execution import (
    AuthorizationDecision,
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
    execute_mission_until_blocked,
)
from app.mission_runtime import (
    MissionDefinition,
    MissionStatus,
    MissionStep,
    new_checkpoint,
)
from app.robot_execution_pinning import (
    RobotCanaryDisposition,
    RobotCanaryHealthSample,
    RobotExecutionPin,
    RobotPinDisposition,
    RobotRegistryRuntimeView,
    build_execution_pin,
    evaluate_canary_health,
    validate_execution_pin,
)
from app.robot_registry_intelligence import (
    ApiCapabilityPlan,
    CompiledPlanKind,
    CompiledRobotPlan,
)

NOW = datetime(2026, 8, 23, 1, 30, tzinfo=UTC)
VERSION_FINGERPRINT = "a" * 64
BASELINE_FINGERPRINT = "b" * 64


def plan() -> CompiledRobotPlan:
    return CompiledRobotPlan(
        tenant_id="YS_TR",
        company_id="company-a",
        objective_id="daily-report",
        robot_id="daily-report-download",
        robot_version=9,
        generation=7,
        kind=CompiledPlanKind.API,
        version_fingerprint=VERSION_FINGERPRINT,
        approval_evidence_ref="approval://robot/v9",
        api_plan=ApiCapabilityPlan(
            capability_ref="reports.export",
            method="POST",
            url="https://api.acme.example/v9/reports/export",
            operation_id="createExportV9",
            expected_outcome_fingerprint="c" * 64,
            side_effect_possible=True,
        ),
    )


def pin(*, canary: bool = False) -> RobotExecutionPin:
    return build_execution_pin(
        plan=plan(),
        mission_id="daily-report-mission",
        lease_id="d" * 64,
        lease_generation=1,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        canary=canary,
        baseline_version=8 if canary else None,
        baseline_version_fingerprint=BASELINE_FINGERPRINT if canary else None,
    )


def runtime(**overrides) -> RobotRegistryRuntimeView:
    values = {
        "tenant_id": "YS_TR",
        "company_id": "company-a",
        "objective_id": "daily-report",
        "robot_id": "daily-report-download",
        "state": "active",
        "active_version": 9,
        "active_version_fingerprint": VERSION_FINGERPRINT,
        "generation": 7,
    }
    values.update(overrides)
    return RobotRegistryRuntimeView(**values)


def mission() -> MissionDefinition:
    return MissionDefinition(
        mission_id="daily-report-mission",
        objective="Export daily report",
        tenant_id="YS_TR",
        steps=(
            MissionStep(
                step_id="export",
                description="Export report through governed robot",
                side_effect=True,
                required_permission="reports.export",
                idempotency_key="daily-report:2026-08-22",
                effect_verifier_ref="report://export/readback",
            ),
        ),
    )


def specs() -> tuple[MissionExecutionSpec, ...]:
    return (
        MissionExecutionSpec(
            step_id="export",
            kind=MissionExecutionKind.CAPABILITY,
            capability_ref="reports.export",
        ),
    )


def test_exact_runtime_view_validates_pin_and_generation_drift_rejects_it():
    current = validate_execution_pin(
        pin=pin(),
        runtime=runtime(),
        phase="pre_dispatch",
        checked_at=NOW + timedelta(minutes=1),
    )
    assert current.disposition is RobotPinDisposition.CURRENT
    assert current.allowed is True

    stale = validate_execution_pin(
        pin=pin(),
        runtime=runtime(
            generation=8,
            active_version=8,
            active_version_fingerprint=BASELINE_FINGERPRINT,
        ),
        phase="pre_dispatch",
        checked_at=NOW + timedelta(minutes=2),
    )
    assert stale.disposition is RobotPinDisposition.STALE
    assert stale.allowed is False
    assert stale.reason_code == "robot_execution_registry_generation_or_version_changed"


def test_expired_execution_pin_fails_closed():
    decision = validate_execution_pin(
        pin=pin(),
        runtime=runtime(),
        phase="pre_dispatch",
        checked_at=NOW + timedelta(hours=1),
    )
    assert decision.disposition is RobotPinDisposition.EXPIRED
    assert decision.allowed is False


def test_canary_incorrect_side_effect_requires_rollback_to_explicit_baseline():
    canary = pin(canary=True)
    decision = evaluate_canary_health(
        pin=canary,
        sample=RobotCanaryHealthSample(
            attempts=3,
            verified_successes=2,
            incorrect_side_effects=1,
            unknown_effects=0,
            holds=0,
            sampled_at=NOW + timedelta(minutes=5),
            evidence_refs=("canary://run/1", "canary://run/2", "canary://run/3"),
        ),
    )
    assert decision.disposition is RobotCanaryDisposition.ROLLBACK_REQUIRED
    assert decision.rollback_target_version == 8
    assert decision.rollback_target_fingerprint == BASELINE_FINGERPRINT
    assert decision.automatic_registry_mutation_authorized is False


def test_healthy_canary_needs_sample_depth_then_becomes_promotion_eligible():
    canary = pin(canary=True)
    early = evaluate_canary_health(
        pin=canary,
        sample=RobotCanaryHealthSample(
            attempts=5,
            verified_successes=5,
            incorrect_side_effects=0,
            unknown_effects=0,
            holds=0,
            sampled_at=NOW + timedelta(minutes=5),
            evidence_refs=("canary://early",),
        ),
    )
    assert early.disposition is RobotCanaryDisposition.CONTINUE

    mature = evaluate_canary_health(
        pin=canary,
        sample=RobotCanaryHealthSample(
            attempts=20,
            verified_successes=20,
            incorrect_side_effects=0,
            unknown_effects=0,
            holds=0,
            sampled_at=NOW + timedelta(minutes=10),
            evidence_refs=("canary://mature",),
        ),
    )
    assert mature.disposition is RobotCanaryDisposition.PROMOTION_ELIGIBLE


def test_generation_change_between_authorization_and_dispatch_prevents_handler_call():
    calls = 0
    phases: list[str] = []

    async def guard(execution_pin, phase):
        phases.append(phase)
        view = runtime() if phase == "pre_authorization" else runtime(
            generation=8,
            active_version=8,
            active_version_fingerprint=BASELINE_FINGERPRINT,
        )
        return validate_execution_pin(
            pin=execution_pin,
            runtime=view,
            phase=phase,
            checked_at=NOW + timedelta(minutes=1),
        )

    async def authorize(definition, step, capability_ref):
        return AuthorizationDecision(allowed=True, evidence_ref="authz://reports.export")

    async def handler(definition, step, state, idempotency_key):
        nonlocal calls
        calls += 1
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            transaction_ref="tx://should-not-run",
            robot_commit_fence_receipt_ref="agent-commit://should-not-run",
        )

    result = asyncio.run(
        execute_mission_until_blocked(
            definition=mission(),
            checkpoint=new_checkpoint(mission()),
            specs=specs(),
            gateway=None,
            reasoning_evidence_writer=lambda receipt: "unused://reasoning",
            capability_handlers={"reports.export": handler},
            authorization_checker=authorize,
            robot_execution_pin=pin(),
            robot_execution_guard=guard,
        )
    )
    assert calls == 0
    assert phases == ["pre_authorization", "pre_dispatch"]
    assert result.transitions_executed == 0
    assert result.checkpoint.status is MissionStatus.READY
    assert (
        "robot_execution_registry_generation_or_version_changed:reports.export"
        in result.blockers
    )


def test_robot_side_effect_without_commit_fence_receipt_halts_as_unknown_authority():
    async def guard(execution_pin, phase):
        return validate_execution_pin(
            pin=execution_pin,
            runtime=runtime(),
            phase=phase,
            checked_at=NOW + timedelta(minutes=1),
        )

    async def authorize(definition, step, capability_ref):
        return AuthorizationDecision(allowed=True, evidence_ref="authz://reports.export")

    async def handler(definition, step, state, idempotency_key):
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            transaction_ref="tx://export-1",
            evidence_refs=("report://export/readback/ok",),
        )

    result = asyncio.run(
        execute_mission_until_blocked(
            definition=mission(),
            checkpoint=new_checkpoint(mission()),
            specs=specs(),
            gateway=None,
            reasoning_evidence_writer=lambda receipt: "unused://reasoning",
            capability_handlers={"reports.export": handler},
            authorization_checker=authorize,
            robot_execution_pin=pin(),
            robot_execution_guard=guard,
        )
    )
    assert result.checkpoint.status is MissionStatus.HALTED
    assert "robot_commit_fence_receipt_missing:reports.export" in result.blockers


def test_robot_side_effect_with_commit_fence_and_effect_receipts_completes():
    async def guard(execution_pin, phase):
        return validate_execution_pin(
            pin=execution_pin,
            runtime=runtime(),
            phase=phase,
            checked_at=NOW + timedelta(minutes=1),
        )

    async def authorize(definition, step, capability_ref):
        return AuthorizationDecision(allowed=True, evidence_ref="authz://reports.export")

    async def handler(definition, step, state, idempotency_key):
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            transaction_ref="tx://export-2",
            evidence_refs=("report://export/readback/ok",),
            robot_commit_fence_receipt_ref="agent-commit://robot-lease-bound/receipt-2",
        )

    result = asyncio.run(
        execute_mission_until_blocked(
            definition=mission(),
            checkpoint=new_checkpoint(mission()),
            specs=specs(),
            gateway=None,
            reasoning_evidence_writer=lambda receipt: "unused://reasoning",
            capability_handlers={"reports.export": handler},
            authorization_checker=authorize,
            robot_execution_pin=pin(),
            robot_execution_guard=guard,
        )
    )
    assert result.checkpoint.status is MissionStatus.COMPLETED
    step = result.checkpoint.steps[0]
    assert "agent-commit://robot-lease-bound/receipt-2" in step.evidence_refs
    assert pin().evidence_ref in step.evidence_refs
