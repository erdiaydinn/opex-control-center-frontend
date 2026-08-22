"""Deterministic replay runtime for qualified Jarvis write procedures.

The healthy path deliberately makes no model call. A qualified procedure is
bound to an exact Playwright workflow shape and environment. Every replay still
requires a fresh identity-bound command authorization, exact idempotency, exact
risk/scope/capability binding, and authoritative effect verification through the
existing Mission Execution + Playwright mission adapter.

Environment drift or an ambiguous write blocks replay before any model repair.
A future repair flow may propose a new procedure revision, but this runtime
never auto-promotes that revision.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from .command_authorization import (
    CommandAuthorizationEnvelope,
    build_mission_command_authorization_checker,
)
from .engine_gateway import EngineGateway
from .mission_execution import (
    CapabilityHandler,
    MissionExecutionKind,
    MissionExecutionSpec,
    MissionExecutionSummary,
    execute_mission_until_blocked,
)
from .mission_runtime import MissionDefinition, MissionStatus, MissionStep, new_checkpoint
from .playwright_computer_runtime import PlaywrightSessionConfig
from .playwright_mission_adapter import PlaywrightCapabilityPlan
from .procedural_memory import ProcedureStatus
from .write_capability_qualification import (
    QualifiedWriteCapability,
    WriteReplayPreflight,
    preflight_qualified_write_replay,
)

QUALIFIED_WRITE_REPLAY_CONTRACT = "eay-qualified-write-replay-v1"


class ReplayDisposition(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    HALTED = "halted"


class QualifiedPlaywrightBinding(BaseModel):
    contract: str = QUALIFIED_WRITE_REPLAY_CONTRACT
    procedure_capability_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    application_id: str = Field(min_length=1)
    execution_capability_ref: str = Field(min_length=1)
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_shape_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    effect_verifier_ref: str = Field(min_length=1)
    model_repair_allowed: bool = False
    auto_promotion_allowed: bool = False

    @model_validator(mode="after")
    def replay_binding_never_enables_model_repair_or_auto_promotion(self) -> "QualifiedPlaywrightBinding":
        if self.model_repair_allowed:
            raise ValueError("qualified_write_replay_healthy_path_forbids_model_repair")
        if self.auto_promotion_allowed:
            raise ValueError("qualified_write_replay_never_auto_promotes_repairs")
        return self


class QualifiedWriteReplayResult(BaseModel):
    contract: str = QUALIFIED_WRITE_REPLAY_CONTRACT
    disposition: ReplayDisposition
    capability_name: str
    procedure_capability_id: str
    plan_shape_fingerprint: str
    model_calls: int = 0
    preflight: WriteReplayPreflight
    mission_summary: MissionExecutionSummary | None = None
    effect_verification_required: bool = True
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def replay_result_preserves_boundaries(self) -> "QualifiedWriteReplayResult":
        if self.model_calls != 0:
            raise ValueError("qualified_write_replay_healthy_path_must_use_zero_model_calls")
        if not self.effect_verification_required:
            raise ValueError("qualified_write_replay_requires_effect_verification")
        if self.disposition is ReplayDisposition.COMPLETED:
            if not self.preflight.allowed:
                raise ValueError("completed_write_replay_requires_allowed_preflight")
            if self.mission_summary is None or self.mission_summary.checkpoint.status is not MissionStatus.COMPLETED:
                raise ValueError("completed_write_replay_requires_completed_mission")
            if self.blockers:
                raise ValueError("completed_write_replay_cannot_have_blockers")
        return self


def _plan_shape_payload(plan: PlaywrightCapabilityPlan) -> dict:
    parsed = urlparse(plan.start_url)
    return {
        "application_id": plan.session_config.application_id,
        "tenant_scope_ref": plan.session_config.tenant_scope_ref,
        "allowed_hosts": sorted(plan.session_config.allowed_hosts),
        "start_host": (parsed.hostname or "").casefold().rstrip("."),
        "start_path": parsed.path or "/",
        "capability_ref": plan.capability_ref,
        "commit_action_id": plan.commit_action_id,
        "actions": [
            {
                "action_id": action.action_id,
                "kind": action.kind.value,
                "locator_kind": action.locator.kind.value,
                "locator_value": action.locator.value,
                "accessible_name": action.locator.accessible_name,
            }
            for action in plan.actions
        ],
    }


def playwright_plan_shape_fingerprint(plan: PlaywrightCapabilityPlan) -> str:
    """Fingerprint stable workflow structure without retaining runtime input values."""

    return hashlib.sha256(
        json.dumps(
            _plan_shape_payload(plan),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def bind_qualified_playwright_write(
    *,
    capability: QualifiedWriteCapability,
    plan: PlaywrightCapabilityPlan,
) -> QualifiedPlaywrightBinding:
    if not capability.deterministic_replay_allowed:
        raise ValueError("playwright_binding_requires_qualified_write_capability")
    if capability.procedure.status is not ProcedureStatus.VALIDATED:
        raise ValueError("playwright_binding_requires_validated_procedure")
    if plan.capability_ref != capability.execution_capability_ref:
        raise ValueError("playwright_binding_execution_capability_mismatch")
    if plan.session_config.application_id != capability.application_id:
        raise ValueError("playwright_binding_application_mismatch")
    if plan.session_config.tenant_scope_ref != capability.tenant_scope_ref:
        raise ValueError("playwright_binding_tenant_mismatch")

    verifier_refs = {
        step.effect_verifier_ref
        for step in capability.procedure.steps
        if step.side_effect and step.effect_verifier_ref is not None
    }
    if len(verifier_refs) != 1:
        raise ValueError("playwright_binding_requires_one_write_effect_verifier")
    effect_verifier_ref = next(iter(verifier_refs))

    return QualifiedPlaywrightBinding(
        procedure_capability_id=capability.procedure.capability_id,
        application_id=capability.application_id,
        execution_capability_ref=capability.execution_capability_ref,
        environment_fingerprint=capability.procedure.environment_fingerprint,
        plan_shape_fingerprint=playwright_plan_shape_fingerprint(plan),
        effect_verifier_ref=effect_verifier_ref,
    )


async def replay_qualified_playwright_write(
    *,
    capability: QualifiedWriteCapability,
    binding: QualifiedPlaywrightBinding,
    plan: PlaywrightCapabilityPlan,
    handler: CapabilityHandler,
    authorization: CommandAuthorizationEnvelope,
    observed_environment_fingerprint: str,
    expected_idempotency_key: str,
) -> QualifiedWriteReplayResult:
    """Run one deterministic, freshly authorized, effect-verified write mission."""

    blockers: list[str] = []
    if binding.procedure_capability_id != capability.procedure.capability_id:
        blockers.append("qualified_write_replay_binding_procedure_mismatch")
    if binding.environment_fingerprint != capability.procedure.environment_fingerprint:
        blockers.append("qualified_write_replay_binding_environment_mismatch")
    if binding.application_id != capability.application_id:
        blockers.append("qualified_write_replay_binding_application_mismatch")
    if binding.execution_capability_ref != capability.execution_capability_ref:
        blockers.append("qualified_write_replay_binding_capability_mismatch")
    if playwright_plan_shape_fingerprint(plan) != binding.plan_shape_fingerprint:
        blockers.append("qualified_write_replay_plan_shape_drift")
    if plan.session_config.tenant_scope_ref != capability.tenant_scope_ref:
        blockers.append("qualified_write_replay_plan_tenant_mismatch")

    preflight = preflight_qualified_write_replay(
        capability=capability,
        authorization=authorization,
        observed_environment_fingerprint=observed_environment_fingerprint,
        expected_idempotency_key=expected_idempotency_key,
    )
    blockers.extend(preflight.blockers)
    blockers = list(dict.fromkeys(blockers))
    if blockers:
        return QualifiedWriteReplayResult(
            disposition=ReplayDisposition.BLOCKED,
            capability_name=capability.capability_name,
            procedure_capability_id=capability.procedure.capability_id,
            plan_shape_fingerprint=binding.plan_shape_fingerprint,
            preflight=preflight,
            blockers=tuple(blockers),
        )

    definition = MissionDefinition(
        mission_id=authorization.mission_id,
        objective=f"Deterministic replay of {capability.capability_name}",
        tenant_id=capability.tenant_scope_ref,
        steps=(
            MissionStep(
                step_id=authorization.step_id,
                description=f"Execute {capability.capability_name}",
                side_effect=True,
                required_permission=capability.required_permission,
                idempotency_key=expected_idempotency_key,
                effect_verifier_ref=binding.effect_verifier_ref,
            ),
        ),
    )
    spec = MissionExecutionSpec(
        step_id=authorization.step_id,
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref=capability.execution_capability_ref,
    )
    summary = await execute_mission_until_blocked(
        definition=definition,
        checkpoint=new_checkpoint(definition),
        specs=(spec,),
        gateway=EngineGateway([]),
        reasoning_evidence_writer=lambda receipt: "unused",
        capability_handlers={capability.execution_capability_ref: handler},
        authorization_checker=build_mission_command_authorization_checker((authorization,)),
    )

    if summary.checkpoint.status is MissionStatus.COMPLETED:
        disposition = ReplayDisposition.COMPLETED
        result_blockers: tuple[str, ...] = ()
    elif summary.checkpoint.status is MissionStatus.HALTED:
        disposition = ReplayDisposition.HALTED
        result_blockers = summary.blockers
    else:
        disposition = ReplayDisposition.BLOCKED
        result_blockers = summary.blockers or ("qualified_write_replay_mission_not_completed",)

    return QualifiedWriteReplayResult(
        disposition=disposition,
        capability_name=capability.capability_name,
        procedure_capability_id=capability.procedure.capability_id,
        plan_shape_fingerprint=binding.plan_shape_fingerprint,
        preflight=preflight,
        mission_summary=summary,
        blockers=result_blockers,
    )
