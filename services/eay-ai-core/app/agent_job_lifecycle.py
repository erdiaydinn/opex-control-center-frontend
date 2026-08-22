"""Durable-state transitions for hierarchical Jarvis agent jobs.

The repository owns persistence and optimistic compare-and-set.  This module owns
deterministic transitions: cancellation epochs, descendant acknowledgement,
late-result rejection and ambiguous side-effect reconciliation.  It does not
start workers or grant tool authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

AGENT_JOB_LIFECYCLE_CONTRACT = "eay-agent-job-lifecycle-v1"


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


class AgentJobStatus(str, Enum):
    ADMITTED = "admitted"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentEffectState(str, Enum):
    NO_EFFECT = "no_effect"
    EFFECT_VERIFIED = "effect_verified"
    UNKNOWN_EFFECT = "unknown_effect"
    RECONCILED_NO_EFFECT = "reconciled_no_effect"


class ChildAgentState(BaseModel):
    child_agent_id: str = Field(min_length=1)
    cancellation_epoch_ack: int = Field(default=0, ge=0)
    completed: bool = False
    result_evidence_refs: tuple[str, ...] = ()
    effect_state: AgentEffectState = AgentEffectState.NO_EFFECT

    @model_validator(mode="after")
    def child_state_is_consistent(self) -> ChildAgentState:
        if len(self.result_evidence_refs) != len(set(self.result_evidence_refs)):
            raise ValueError("agent_child_result_evidence_must_be_unique")
        if self.completed and not self.result_evidence_refs:
            raise ValueError("completed_agent_child_requires_evidence")
        return self


class AgentJobSnapshot(BaseModel):
    contract: str = AGENT_JOB_LIFECYCLE_CONTRACT
    job_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    root_agent_id: str = Field(min_length=1)
    status: AgentJobStatus = AgentJobStatus.ADMITTED
    version: int = Field(default=0, ge=0)
    cancellation_epoch: int = Field(default=0, ge=0)
    required_child_agent_ids: tuple[str, ...] = Field(min_length=1)
    children: tuple[ChildAgentState, ...] = Field(min_length=1)
    cancel_requested_at: datetime | None = None
    terminal_at: datetime | None = None
    lifecycle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    business_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def snapshot_is_integrity_bound(self) -> AgentJobSnapshot:
        if self.business_execution_authority_granted:
            raise ValueError("agent_job_lifecycle_never_grants_business_execution_authority")
        child_ids = [item.child_agent_id for item in self.children]
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("agent_job_child_ids_must_be_unique")
        if set(child_ids) != set(self.required_child_agent_ids):
            raise ValueError("agent_job_required_children_mismatch")
        if len(self.required_child_agent_ids) != len(set(self.required_child_agent_ids)):
            raise ValueError("agent_job_required_children_must_be_unique")
        if self.cancel_requested_at:
            _aware(self.cancel_requested_at, "agent_job_cancel_time_requires_timezone")
        if self.terminal_at:
            _aware(self.terminal_at, "agent_job_terminal_time_requires_timezone")
        if (
            self.status in {AgentJobStatus.CANCELLED, AgentJobStatus.COMPLETED, AgentJobStatus.FAILED}
            and self.terminal_at is None
        ):
            raise ValueError("terminal_agent_job_requires_timestamp")
        if self.lifecycle_fingerprint != _hash(_snapshot_payload(self)):
            raise ValueError("agent_job_lifecycle_fingerprint_mismatch")
        return self


def _snapshot_payload(snapshot: AgentJobSnapshot) -> dict[str, object]:
    return {
        "contract": snapshot.contract,
        "job_id": snapshot.job_id,
        "objective_ref": snapshot.objective_ref,
        "tenant_id": snapshot.tenant_id,
        "root_agent_id": snapshot.root_agent_id,
        "status": snapshot.status.value,
        "version": snapshot.version,
        "cancellation_epoch": snapshot.cancellation_epoch,
        "required_child_agent_ids": list(snapshot.required_child_agent_ids),
        "children": [item.model_dump(mode="json") for item in snapshot.children],
        "cancel_requested_at": snapshot.cancel_requested_at.isoformat() if snapshot.cancel_requested_at else None,
        "terminal_at": snapshot.terminal_at.isoformat() if snapshot.terminal_at else None,
        "business_execution_authority_granted": False,
    }


def _build(**values) -> AgentJobSnapshot:
    values["children"] = tuple(
        item if isinstance(item, ChildAgentState) else ChildAgentState.model_validate(item)
        for item in values["children"]
    )
    values["status"] = AgentJobStatus(values["status"])
    provisional = AgentJobSnapshot.model_construct(
        contract=AGENT_JOB_LIFECYCLE_CONTRACT,
        business_execution_authority_granted=False,
        lifecycle_fingerprint="0" * 64,
        **values,
    )
    return AgentJobSnapshot(
        **values,
        lifecycle_fingerprint=_hash(_snapshot_payload(provisional)),
    )


def new_agent_job(
    *,
    job_id: str,
    objective_ref: str,
    tenant_id: str,
    root_agent_id: str,
    child_agent_ids: tuple[str, ...],
) -> AgentJobSnapshot:
    if not child_agent_ids or len(child_agent_ids) != len(set(child_agent_ids)):
        raise ValueError("agent_job_requires_unique_children")
    return _build(
        job_id=job_id,
        objective_ref=objective_ref,
        tenant_id=tenant_id,
        root_agent_id=root_agent_id,
        status=AgentJobStatus.ADMITTED,
        version=0,
        cancellation_epoch=0,
        required_child_agent_ids=child_agent_ids,
        children=tuple(ChildAgentState(child_agent_id=item) for item in child_agent_ids),
        cancel_requested_at=None,
        terminal_at=None,
    )


def mark_agent_job_running(snapshot: AgentJobSnapshot) -> AgentJobSnapshot:
    snapshot = AgentJobSnapshot.model_validate(snapshot.model_dump(mode="json"))
    if snapshot.status is AgentJobStatus.RUNNING:
        return snapshot
    if snapshot.status is not AgentJobStatus.ADMITTED:
        raise ValueError("agent_job_cannot_start_from_current_status")
    return _build(**{
        **snapshot.model_dump(exclude={"contract", "lifecycle_fingerprint", "business_execution_authority_granted"}),
        "status": AgentJobStatus.RUNNING,
        "version": snapshot.version + 1,
    })


def request_agent_job_cancellation(
    snapshot: AgentJobSnapshot,
    *,
    now: datetime,
) -> AgentJobSnapshot:
    snapshot = AgentJobSnapshot.model_validate(snapshot.model_dump(mode="json"))
    _aware(now, "agent_job_cancel_time_requires_timezone")
    if snapshot.status in {AgentJobStatus.CANCELLED, AgentJobStatus.COMPLETED, AgentJobStatus.FAILED}:
        return snapshot
    if snapshot.status in {AgentJobStatus.CANCEL_REQUESTED, AgentJobStatus.RECONCILIATION_REQUIRED}:
        return snapshot
    unknown = any(item.effect_state is AgentEffectState.UNKNOWN_EFFECT for item in snapshot.children)
    return _build(**{
        **snapshot.model_dump(exclude={"contract", "lifecycle_fingerprint", "business_execution_authority_granted"}),
        "status": AgentJobStatus.RECONCILIATION_REQUIRED if unknown else AgentJobStatus.CANCEL_REQUESTED,
        "version": snapshot.version + 1,
        "cancellation_epoch": snapshot.cancellation_epoch + 1,
        "cancel_requested_at": now,
    })


def record_child_result(
    snapshot: AgentJobSnapshot,
    *,
    child_agent_id: str,
    observed_cancellation_epoch: int,
    evidence_refs: tuple[str, ...],
    effect_state: AgentEffectState,
    now: datetime,
) -> AgentJobSnapshot:
    snapshot = AgentJobSnapshot.model_validate(snapshot.model_dump(mode="json"))
    _aware(now, "agent_job_child_result_time_requires_timezone")
    if snapshot.status in {AgentJobStatus.CANCELLED, AgentJobStatus.COMPLETED, AgentJobStatus.FAILED}:
        raise ValueError("agent_job_terminal_rejects_child_result")
    if observed_cancellation_epoch != snapshot.cancellation_epoch:
        raise ValueError("agent_job_stale_cancellation_epoch")
    if snapshot.status in {AgentJobStatus.CANCEL_REQUESTED, AgentJobStatus.RECONCILIATION_REQUIRED}:
        raise ValueError("agent_job_cancelled_tree_rejects_late_result")
    if not evidence_refs or len(evidence_refs) != len(set(evidence_refs)):
        raise ValueError("agent_job_child_result_requires_unique_evidence")
    child_map = {item.child_agent_id: item for item in snapshot.children}
    child = child_map.get(child_agent_id)
    if child is None:
        raise ValueError("agent_job_unknown_child")
    proposed = ChildAgentState(
        child_agent_id=child_agent_id,
        cancellation_epoch_ack=observed_cancellation_epoch,
        completed=True,
        result_evidence_refs=evidence_refs,
        effect_state=effect_state,
    )
    if child.completed:
        if child == proposed:
            return snapshot
        raise ValueError("agent_job_child_result_conflict")
    child_map[child_agent_id] = proposed
    children = tuple(child_map[item] for item in snapshot.required_child_agent_ids)
    complete = all(item.completed for item in children)
    unknown = any(item.effect_state is AgentEffectState.UNKNOWN_EFFECT for item in children)
    status = AgentJobStatus.RECONCILIATION_REQUIRED if unknown else (
        AgentJobStatus.COMPLETED if complete else AgentJobStatus.RUNNING
    )
    return _build(**{
        **snapshot.model_dump(exclude={"contract", "lifecycle_fingerprint", "business_execution_authority_granted", "children", "status", "version", "terminal_at"}),
        "children": children,
        "status": status,
        "version": snapshot.version + 1,
        "terminal_at": now if status is AgentJobStatus.COMPLETED else None,
    })


def acknowledge_agent_job_cancellation(
    snapshot: AgentJobSnapshot,
    *,
    child_agent_id: str,
    cancellation_epoch: int,
    effect_state: AgentEffectState,
    evidence_refs: tuple[str, ...],
    now: datetime,
) -> AgentJobSnapshot:
    snapshot = AgentJobSnapshot.model_validate(snapshot.model_dump(mode="json"))
    _aware(now, "agent_job_cancel_ack_time_requires_timezone")
    if snapshot.status not in {AgentJobStatus.CANCEL_REQUESTED, AgentJobStatus.RECONCILIATION_REQUIRED}:
        raise ValueError("agent_job_not_cancelling")
    if cancellation_epoch != snapshot.cancellation_epoch:
        raise ValueError("agent_job_stale_cancellation_epoch")
    if effect_state is AgentEffectState.EFFECT_VERIFIED:
        raise ValueError("cancel_ack_cannot_claim_verified_effect")
    if not evidence_refs or len(evidence_refs) != len(set(evidence_refs)):
        raise ValueError("agent_job_cancel_ack_requires_unique_evidence")
    child_map = {item.child_agent_id: item for item in snapshot.children}
    child = child_map.get(child_agent_id)
    if child is None:
        raise ValueError("agent_job_unknown_child")
    if child.cancellation_epoch_ack == cancellation_epoch and child.result_evidence_refs:
        return snapshot
    child_map[child_agent_id] = ChildAgentState(
        child_agent_id=child_agent_id,
        cancellation_epoch_ack=cancellation_epoch,
        completed=False,
        result_evidence_refs=evidence_refs,
        effect_state=effect_state,
    )
    children = tuple(child_map[item] for item in snapshot.required_child_agent_ids)
    all_ack = all(item.cancellation_epoch_ack == cancellation_epoch for item in children)
    unknown = any(item.effect_state is AgentEffectState.UNKNOWN_EFFECT for item in children)
    status = AgentJobStatus.RECONCILIATION_REQUIRED if unknown else (
        AgentJobStatus.CANCELLED if all_ack else AgentJobStatus.CANCEL_REQUESTED
    )
    return _build(**{
        **snapshot.model_dump(exclude={"contract", "lifecycle_fingerprint", "business_execution_authority_granted", "children", "status", "version", "terminal_at"}),
        "children": children,
        "status": status,
        "version": snapshot.version + 1,
        "terminal_at": now if status is AgentJobStatus.CANCELLED else None,
    })
