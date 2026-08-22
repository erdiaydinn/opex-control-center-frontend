"""End-to-end mission execution fabric for Jarvis.

This layer composes the existing durable mission state machine with the real
engine gateway and capability handlers. It is intentionally small and strict:
- reasoning steps use the router-backed EngineGateway;
- permissioned actions require authorization evidence;
- live-company-dependent steps require an integrity-valid DecisionTruthReceipt;
- robot-backed capability execution must retain an exact version/generation pin;
- side effects are never marked successful without authoritative effect
  verification;
- robot-backed side effects additionally require a commit-fence receipt bound to
  the exact robot execution lease;
- ambiguous write outcomes halt the mission instead of retrying blindly;
- checkpoints remain the durable source of resume truth.

The fabric does not expose provider-native tools. Enterprise actions remain EAY
capabilities behind EAY authorization, live-truth readiness, idempotency,
effect verification and audit evidence.
"""

from __future__ import annotations

from enum import Enum
from typing import Awaitable, Callable, Mapping

from pydantic import BaseModel, Field, model_validator

from .decision_truth_integrity import validate_decision_truth_receipt_integrity
from .engine_gateway import EngineGateway, EngineInvocationReceipt
from .intelligence_router import IntelligenceTask
from .live_company_readiness import DecisionTruthReceipt, DecisionTruthStatus
from .mission_runtime import (
    MissionCheckpoint,
    MissionDefinition,
    MissionStatus,
    MissionStep,
    StepCheckpoint,
    record_step_result,
    runnable_steps,
)
from .robot_execution_pinning import RobotExecutionGuardDecision, RobotExecutionPin

MISSION_EXECUTION_CONTRACT = "eay-mission-execution-fabric-v1"


class MissionExecutionKind(str, Enum):
    REASONING = "reasoning"
    CAPABILITY = "capability"


class MissionExecutionSpec(BaseModel):
    step_id: str = Field(min_length=1)
    kind: MissionExecutionKind
    intelligence_task: IntelligenceTask | None = None
    prompt: str | None = None
    capability_ref: str | None = None
    decision_truth_requirement_id: str | None = None
    requires_firm_company_truth: bool = False

    @model_validator(mode="after")
    def kind_contract(self) -> "MissionExecutionSpec":
        if self.kind is MissionExecutionKind.REASONING:
            if self.intelligence_task is None or not (self.prompt or "").strip():
                raise ValueError("reasoning_step_requires_task_and_prompt")
            if self.capability_ref is not None:
                raise ValueError("reasoning_step_cannot_define_capability")
        else:
            if not (self.capability_ref or "").strip():
                raise ValueError("capability_step_requires_capability_ref")
            if self.intelligence_task is not None or self.prompt is not None:
                raise ValueError("capability_step_cannot_define_reasoning_payload")
        if self.requires_firm_company_truth and not self.decision_truth_requirement_id:
            raise ValueError("firm_company_truth_requires_truth_requirement_id")
        return self


class AuthorizationDecision(BaseModel):
    allowed: bool
    evidence_ref: str | None = None
    reason_code: str | None = None

    @model_validator(mode="after")
    def allowed_requires_evidence(self) -> "AuthorizationDecision":
        if self.allowed and not self.evidence_ref:
            raise ValueError("authorization_allow_requires_evidence_ref")
        return self


class CapabilityExecutionOutcome(BaseModel):
    succeeded: bool
    effect_verified: bool = False
    ambiguous_outcome: bool = False
    evidence_refs: tuple[str, ...] = ()
    transaction_ref: str | None = None
    robot_commit_fence_receipt_ref: str | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def outcome_is_consistent(self) -> "CapabilityExecutionOutcome":
        if self.succeeded and self.ambiguous_outcome:
            raise ValueError("capability_outcome_cannot_be_success_and_ambiguous")
        if self.effect_verified and not self.succeeded:
            raise ValueError("failed_capability_cannot_claim_verified_effect")
        if self.robot_commit_fence_receipt_ref is not None and not self.robot_commit_fence_receipt_ref.strip():
            raise ValueError("robot_commit_fence_receipt_ref_must_be_non_empty")
        return self


class MissionExecutionSummary(BaseModel):
    contract: str = MISSION_EXECUTION_CONTRACT
    checkpoint: MissionCheckpoint
    transitions_executed: int = Field(ge=0)
    reasoning_engine_ids: tuple[str, ...] = ()
    capability_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()


ReasoningEvidenceWriter = Callable[[EngineInvocationReceipt], str]
AuthorizationChecker = Callable[[MissionDefinition, MissionStep, str], Awaitable[AuthorizationDecision]]
CapabilityHandler = Callable[
    [MissionDefinition, MissionStep, StepCheckpoint, str],
    Awaitable[CapabilityExecutionOutcome],
]
RobotExecutionGuard = Callable[
    [RobotExecutionPin, str],
    Awaitable[RobotExecutionGuardDecision],
]


def _step_map(definition: MissionDefinition) -> dict[str, MissionStep]:
    return {item.step_id: item for item in definition.steps}


def _state_map(checkpoint: MissionCheckpoint) -> dict[str, StepCheckpoint]:
    return {item.step_id: item for item in checkpoint.steps}


def _truth_receipt_ref(receipt: DecisionTruthReceipt) -> str:
    return (
        "live-truth-readiness://"
        + receipt.tenant_id
        + "/"
        + receipt.requirement_id
        + "/"
        + receipt.status.value
        + "/"
        + receipt.receipt_fingerprint
    )


def _truth_gate_blocker(
    *,
    definition: MissionDefinition,
    spec: MissionExecutionSpec,
    receipts: Mapping[str, DecisionTruthReceipt],
) -> tuple[str | None, str | None]:
    requirement_id = spec.decision_truth_requirement_id
    if not requirement_id:
        return None, None

    receipt = receipts.get(requirement_id)
    if receipt is None:
        return "live_company_truth_receipt_missing", None
    try:
        receipt = validate_decision_truth_receipt_integrity(receipt)
    except ValueError:
        return "live_company_truth_receipt_invalid", None
    if receipt.requirement_id != requirement_id:
        return "live_company_truth_requirement_mismatch", None
    if receipt.tenant_id != definition.tenant_id:
        return "live_company_truth_tenant_mismatch", None
    if receipt.status is DecisionTruthStatus.BLOCKED:
        return "live_company_truth_blocked", None
    if spec.requires_firm_company_truth and not receipt.firm_claim_authorized:
        return "live_company_firm_claim_not_authorized", None
    return None, _truth_receipt_ref(receipt)


async def _robot_guard(
    *,
    pin: RobotExecutionPin,
    guard: RobotExecutionGuard,
    phase: str,
) -> RobotExecutionGuardDecision:
    decision = await guard(pin, phase)
    return RobotExecutionGuardDecision.model_validate(decision.model_dump(mode="json"))


async def execute_mission_until_blocked(
    *,
    definition: MissionDefinition,
    checkpoint: MissionCheckpoint,
    specs: tuple[MissionExecutionSpec, ...],
    gateway: EngineGateway,
    reasoning_evidence_writer: ReasoningEvidenceWriter,
    capability_handlers: Mapping[str, CapabilityHandler],
    authorization_checker: AuthorizationChecker | None = None,
    decision_truth_receipts: Mapping[str, DecisionTruthReceipt] | None = None,
    robot_execution_pin: RobotExecutionPin | None = None,
    robot_execution_guard: RobotExecutionGuard | None = None,
    max_transitions: int = 100,
) -> MissionExecutionSummary:
    if max_transitions < 1:
        raise ValueError("mission_execution_max_transitions_must_be_positive")
    if (robot_execution_pin is None) != (robot_execution_guard is None):
        raise ValueError("mission_robot_execution_pin_and_guard_must_be_paired")
    if robot_execution_pin is not None:
        robot_execution_pin = RobotExecutionPin.model_validate(
            robot_execution_pin.model_dump(mode="json")
        )
        if robot_execution_pin.tenant_id != definition.tenant_id:
            raise ValueError("mission_robot_execution_pin_tenant_mismatch")
        if robot_execution_pin.mission_id != definition.mission_id:
            raise ValueError("mission_robot_execution_pin_mission_mismatch")

    spec_map = {item.step_id: item for item in specs}
    if len(spec_map) != len(specs):
        raise ValueError("mission_execution_step_specs_must_be_unique")
    expected_steps = {item.step_id for item in definition.steps}
    if set(spec_map) != expected_steps:
        raise ValueError("mission_execution_specs_must_cover_definition_exactly")

    truth_receipts = decision_truth_receipts or {}
    current = checkpoint
    steps = _step_map(definition)
    transitions = 0
    reasoning_engines: list[str] = []
    capabilities: list[str] = []
    blockers: list[str] = []

    while transitions < max_transitions:
        runnable = runnable_steps(definition, current)
        if not runnable:
            break
        step_id = runnable[0]
        step = steps[step_id]
        state = _state_map(current)[step_id]
        spec = spec_map[step_id]

        truth_blocker, truth_receipt_ref = _truth_gate_blocker(
            definition=definition,
            spec=spec,
            receipts=truth_receipts,
        )
        if truth_blocker is not None:
            blockers.append(truth_blocker + ":" + step_id)
            break
        truth_evidence = (() if truth_receipt_ref is None else (truth_receipt_ref,))

        if spec.kind is MissionExecutionKind.REASONING:
            if step.side_effect:
                current = record_step_result(
                    definition,
                    current,
                    step_id=step_id,
                    succeeded=False,
                    error="reasoning_step_cannot_execute_side_effect",
                )
                blockers.append("reasoning_step_cannot_execute_side_effect:" + step_id)
                transitions += 1
                continue
            try:
                receipt = await gateway.invoke_primary(
                    task=spec.intelligence_task,
                    prompt=spec.prompt or "",
                )
                evidence_ref = reasoning_evidence_writer(receipt)
                if not evidence_ref.strip():
                    raise ValueError("reasoning_evidence_writer_returned_empty_ref")
            except Exception as exc:  # sanitized at the mission boundary
                error_code = f"reasoning_execution_failed:{type(exc).__name__}"
                current = record_step_result(
                    definition,
                    current,
                    step_id=step_id,
                    succeeded=False,
                    error=error_code,
                )
                blockers.append(error_code + ":" + step_id)
            else:
                current = record_step_result(
                    definition,
                    current,
                    step_id=step_id,
                    succeeded=True,
                    evidence_refs=tuple(dict.fromkeys((*truth_evidence, evidence_ref))),
                )
                reasoning_engines.append(receipt.engine_id)
            transitions += 1
            continue

        capability_ref = spec.capability_ref or ""
        capabilities.append(capability_ref)
        handler = capability_handlers.get(capability_ref)
        if handler is None:
            current = record_step_result(
                definition,
                current,
                step_id=step_id,
                succeeded=False,
                error="capability_handler_not_registered",
            )
            blockers.append("capability_handler_not_registered:" + capability_ref)
            transitions += 1
            continue

        robot_evidence: tuple[str, ...] = ()
        if robot_execution_pin is not None and robot_execution_guard is not None:
            pre_auth = await _robot_guard(
                pin=robot_execution_pin,
                guard=robot_execution_guard,
                phase="pre_authorization",
            )
            if not pre_auth.allowed:
                blockers.append((pre_auth.reason_code or "robot_execution_pin_rejected") + ":" + capability_ref)
                break
            robot_evidence = tuple(
                dict.fromkeys((robot_execution_pin.evidence_ref, pre_auth.evidence_ref))
            )

        authorization_evidence: tuple[str, ...] = tuple(
            dict.fromkeys((*truth_evidence, *robot_evidence))
        )
        if step.required_permission:
            if authorization_checker is None:
                decision = AuthorizationDecision(
                    allowed=False,
                    reason_code="authorization_checker_missing",
                )
            else:
                decision = await authorization_checker(definition, step, capability_ref)
            if not decision.allowed:
                current = record_step_result(
                    definition,
                    current,
                    step_id=step_id,
                    succeeded=False,
                    error=decision.reason_code or "capability_authorization_denied",
                )
                blockers.append(
                    (decision.reason_code or "capability_authorization_denied") + ":" + capability_ref
                )
                transitions += 1
                continue
            authorization_evidence = tuple(
                dict.fromkeys((*authorization_evidence, decision.evidence_ref or ""))
            )

        if robot_execution_pin is not None and robot_execution_guard is not None:
            pre_dispatch = await _robot_guard(
                pin=robot_execution_pin,
                guard=robot_execution_guard,
                phase="pre_dispatch",
            )
            if not pre_dispatch.allowed:
                blockers.append(
                    (pre_dispatch.reason_code or "robot_execution_pin_rejected")
                    + ":"
                    + capability_ref
                )
                break
            authorization_evidence = tuple(
                dict.fromkeys((*authorization_evidence, pre_dispatch.evidence_ref))
            )

        try:
            outcome = await handler(
                definition,
                step,
                state,
                step.idempotency_key or "",
            )
        except Exception as exc:
            error_code = f"capability_execution_failed:{type(exc).__name__}"
            current = record_step_result(
                definition,
                current,
                step_id=step_id,
                succeeded=False,
                error=error_code,
            )
            blockers.append(error_code + ":" + capability_ref)
            transitions += 1
            continue

        evidence_refs = tuple(
            dict.fromkeys(
                (
                    *authorization_evidence,
                    *outcome.evidence_refs,
                    *(() if outcome.transaction_ref is None else (outcome.transaction_ref,)),
                    *(
                        ()
                        if outcome.robot_commit_fence_receipt_ref is None
                        else (outcome.robot_commit_fence_receipt_ref,)
                    ),
                )
            )
        )

        if (
            robot_execution_pin is not None
            and step.side_effect
            and outcome.succeeded
            and outcome.robot_commit_fence_receipt_ref is None
        ):
            current = record_step_result(
                definition,
                current,
                step_id=step_id,
                succeeded=False,
                evidence_refs=evidence_refs,
                error="robot_side_effect_missing_commit_fence_receipt",
                ambiguous_outcome=True,
            )
            blockers.append("robot_commit_fence_receipt_missing:" + capability_ref)
            transitions += 1
            break

        if step.side_effect and outcome.succeeded and not outcome.effect_verified:
            current = record_step_result(
                definition,
                current,
                step_id=step_id,
                succeeded=False,
                evidence_refs=evidence_refs,
                error="side_effect_succeeded_without_authoritative_verification",
                ambiguous_outcome=True,
            )
            blockers.append("side_effect_effect_verification_missing:" + capability_ref)
            transitions += 1
            break

        current = record_step_result(
            definition,
            current,
            step_id=step_id,
            succeeded=outcome.succeeded,
            evidence_refs=evidence_refs,
            error=outcome.error_code,
            ambiguous_outcome=outcome.ambiguous_outcome,
        )
        transitions += 1
        if outcome.ambiguous_outcome:
            blockers.append("capability_outcome_ambiguous:" + capability_ref)
            break

    if transitions >= max_transitions and current.status not in {
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.HALTED,
    }:
        blockers.append("mission_execution_transition_budget_exhausted")

    return MissionExecutionSummary(
        checkpoint=current,
        transitions_executed=transitions,
        reasoning_engine_ids=tuple(reasoning_engines),
        capability_refs=tuple(capabilities),
        blockers=tuple(dict.fromkeys(blockers)),
    )
