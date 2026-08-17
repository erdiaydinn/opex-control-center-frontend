"""Durable, resumable mission execution state for Jarvis.

The runtime owns planning state, dependency order, retries and checkpoint
integrity.  It deliberately does not execute tools itself.  Side-effecting
steps require idempotency and effect-verification metadata, and ambiguous
outcomes halt rather than replaying a write blindly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator

MISSION_RUNTIME_CONTRACT = "eay-durable-mission-runtime-v1"


class MissionStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class MissionStep(BaseModel):
    step_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    max_attempts: int = Field(default=2, ge=1, le=10)
    side_effect: bool = False
    irreversible: bool = False
    requires_human_approval: bool = False
    required_permission: str | None = None
    idempotency_key: str | None = None
    effect_verifier_ref: str | None = None

    @model_validator(mode="after")
    def side_effect_contract_is_explicit(self) -> "MissionStep":
        if self.side_effect and not self.idempotency_key:
            raise ValueError("mission_side_effect_requires_idempotency_key")
        if self.side_effect and not self.effect_verifier_ref:
            raise ValueError("mission_side_effect_requires_effect_verifier")
        if self.irreversible and not self.requires_human_approval:
            raise ValueError("mission_irreversible_step_requires_human_approval")
        return self


class MissionDefinition(BaseModel):
    contract: str = MISSION_RUNTIME_CONTRACT
    mission_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    steps: tuple[MissionStep, ...]

    @model_validator(mode="after")
    def graph_is_valid(self) -> "MissionDefinition":
        if not self.steps:
            raise ValueError("mission_requires_steps")
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("mission_step_ids_must_be_unique")
        known = set(ids)
        for step in self.steps:
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError("mission_dependency_unknown:" + ",".join(sorted(unknown)))
            if step.step_id in step.depends_on:
                raise ValueError("mission_step_cannot_depend_on_itself")

        graph = {step.step_id: set(step.depends_on) for step in self.steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in visiting:
                raise ValueError("mission_dependency_cycle")
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)
        return self

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StepCheckpoint(BaseModel):
    step_id: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    approval_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    last_error: str | None = None
    ambiguous_outcome: bool = False


class MissionCheckpoint(BaseModel):
    contract: str = MISSION_RUNTIME_CONTRACT
    mission_id: str
    tenant_id: str
    definition_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: MissionStatus
    steps: tuple[StepCheckpoint, ...]
    checkpointed_at: datetime
    sequence: int = Field(ge=0)

    @model_validator(mode="after")
    def checkpoint_time_is_aware(self) -> "MissionCheckpoint":
        if self.checkpointed_at.tzinfo is None or self.checkpointed_at.utcoffset() is None:
            raise ValueError("mission_checkpoint_requires_timezone")
        return self


def new_checkpoint(definition: MissionDefinition, *, now: datetime | None = None) -> MissionCheckpoint:
    return MissionCheckpoint(
        mission_id=definition.mission_id,
        tenant_id=definition.tenant_id,
        definition_fingerprint=definition.fingerprint(),
        status=MissionStatus.READY,
        steps=tuple(StepCheckpoint(step_id=step.step_id) for step in definition.steps),
        checkpointed_at=now or datetime.now(timezone.utc),
        sequence=0,
    )


def _validate_checkpoint(definition: MissionDefinition, checkpoint: MissionCheckpoint) -> None:
    if checkpoint.mission_id != definition.mission_id or checkpoint.tenant_id != definition.tenant_id:
        raise ValueError("mission_checkpoint_identity_mismatch")
    if checkpoint.definition_fingerprint != definition.fingerprint():
        raise ValueError("mission_checkpoint_definition_drift")
    expected = {step.step_id for step in definition.steps}
    actual = {step.step_id for step in checkpoint.steps}
    if expected != actual:
        raise ValueError("mission_checkpoint_step_set_mismatch")


def runnable_steps(definition: MissionDefinition, checkpoint: MissionCheckpoint) -> tuple[str, ...]:
    _validate_checkpoint(definition, checkpoint)
    if checkpoint.status in {MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.HALTED}:
        return ()

    state = {item.step_id: item for item in checkpoint.steps}
    runnable: list[str] = []
    for step in definition.steps:
        current = state[step.step_id]
        if current.status is not StepStatus.PENDING:
            continue
        if any(state[dependency].status is not StepStatus.SUCCEEDED for dependency in step.depends_on):
            continue
        if step.requires_human_approval and not current.approval_ref:
            continue
        if current.attempts >= step.max_attempts:
            continue
        runnable.append(step.step_id)
    return tuple(runnable)


def with_approval(
    definition: MissionDefinition,
    checkpoint: MissionCheckpoint,
    *,
    step_id: str,
    approval_ref: str,
    now: datetime | None = None,
) -> MissionCheckpoint:
    _validate_checkpoint(definition, checkpoint)
    step_map = {step.step_id: step for step in definition.steps}
    if step_id not in step_map:
        raise KeyError("mission_step_not_found")
    if not step_map[step_id].requires_human_approval:
        raise ValueError("mission_step_does_not_require_approval")
    updated = []
    for item in checkpoint.steps:
        updated.append(item.model_copy(update={"approval_ref": approval_ref}) if item.step_id == step_id else item)
    return checkpoint.model_copy(
        update={
            "steps": tuple(updated),
            "checkpointed_at": now or datetime.now(timezone.utc),
            "sequence": checkpoint.sequence + 1,
        }
    )


def record_step_result(
    definition: MissionDefinition,
    checkpoint: MissionCheckpoint,
    *,
    step_id: str,
    succeeded: bool,
    evidence_refs: tuple[str, ...] = (),
    error: str | None = None,
    ambiguous_outcome: bool = False,
    now: datetime | None = None,
) -> MissionCheckpoint:
    _validate_checkpoint(definition, checkpoint)
    definitions = {step.step_id: step for step in definition.steps}
    states = {item.step_id: item for item in checkpoint.steps}
    if step_id not in definitions:
        raise KeyError("mission_step_not_found")
    step = definitions[step_id]
    current = states[step_id]

    if current.status not in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.FAILED}:
        raise ValueError("mission_step_result_invalid_state")
    if any(states[dependency].status is not StepStatus.SUCCEEDED for dependency in step.depends_on):
        raise ValueError("mission_step_dependencies_incomplete")
    if step.requires_human_approval and not current.approval_ref:
        raise ValueError("mission_step_approval_missing")
    if current.attempts >= step.max_attempts:
        raise ValueError("mission_step_retry_budget_exhausted")

    attempts = current.attempts + 1
    if ambiguous_outcome:
        next_step_status = StepStatus.BLOCKED
        next_mission_status = MissionStatus.HALTED
        error = error or "ambiguous_side_effect_outcome"
    elif succeeded:
        next_step_status = StepStatus.SUCCEEDED
        next_mission_status = MissionStatus.RUNNING
    elif attempts >= step.max_attempts:
        next_step_status = StepStatus.FAILED
        next_mission_status = MissionStatus.FAILED
    else:
        next_step_status = StepStatus.PENDING
        next_mission_status = MissionStatus.RUNNING

    updated_steps: list[StepCheckpoint] = []
    for item in checkpoint.steps:
        if item.step_id != step_id:
            updated_steps.append(item)
            continue
        updated_steps.append(
            item.model_copy(
                update={
                    "status": next_step_status,
                    "attempts": attempts,
                    "evidence_refs": tuple(dict.fromkeys((*item.evidence_refs, *evidence_refs))),
                    "last_error": error,
                    "ambiguous_outcome": ambiguous_outcome,
                }
            )
        )

    if next_mission_status not in {MissionStatus.HALTED, MissionStatus.FAILED} and all(
        item.status is StepStatus.SUCCEEDED for item in updated_steps
    ):
        next_mission_status = MissionStatus.COMPLETED

    return checkpoint.model_copy(
        update={
            "status": next_mission_status,
            "steps": tuple(updated_steps),
            "checkpointed_at": now or datetime.now(timezone.utc),
            "sequence": checkpoint.sequence + 1,
        }
    )


def resume_plan(definition: MissionDefinition, checkpoint: MissionCheckpoint) -> tuple[str, ...]:
    """Return only dependency-safe steps that may resume from the checkpoint."""

    return runnable_steps(definition, checkpoint)
