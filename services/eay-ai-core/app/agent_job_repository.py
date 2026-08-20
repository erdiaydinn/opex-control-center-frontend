"""Durable repository contract for governed Jarvis child-agent jobs.

This module deliberately contains no process-local or SQLite implementation.  It
defines the aggregate, hash-chained event ledger and atomic persistence port that a
PostgreSQL adapter must implement.  Domain transitions are deterministic, tenant
bound and protected by an expected aggregate version.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

AGENT_JOB_REPOSITORY_CONTRACT = "eay-agent-job-repository-v1"
GENESIS_EVENT_HASH = "0" * 64


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


class AgentJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RECOVERY_REQUIRED = "recovery_required"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentJobEventKind(str, Enum):
    CREATED = "created"
    STARTED = "started"
    CHECKPOINTED = "checkpointed"
    RECOVERY_REQUESTED = "recovery_requested"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL = {
    AgentJobStatus.COMPLETED,
    AgentJobStatus.FAILED,
    AgentJobStatus.CANCELLED,
}


class AgentJobCreate(BaseModel):
    contract: str = AGENT_JOB_REPOSITORY_CONTRACT
    tenant_id: str = Field(min_length=1, max_length=160)
    requested_by: str = Field(min_length=1, max_length=240)
    idempotency_key: str = Field(min_length=8, max_length=240)
    objective_ref: str = Field(min_length=1, max_length=500)
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_job_id: str | None = Field(default=None, min_length=1, max_length=160)
    created_at: datetime

    @model_validator(mode="after")
    def valid_create(self) -> AgentJobCreate:
        _aware(self.created_at, "agent_job_created_at_requires_timezone")
        return self


class AgentJobEvent(BaseModel):
    contract: str = AGENT_JOB_REPOSITORY_CONTRACT
    event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence: int = Field(ge=1)
    kind: AgentJobEventKind
    occurred_at: datetime
    actor_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    checkpoint_ref: str | None = None
    blocker_codes: tuple[str, ...] = ()
    previous_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def valid_event(self) -> AgentJobEvent:
        _aware(self.occurred_at, "agent_job_event_time_requires_timezone")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("agent_job_event_evidence_refs_must_be_unique")
        if len(self.blocker_codes) != len(set(self.blocker_codes)):
            raise ValueError("agent_job_event_blockers_must_be_unique")
        if self.event_hash != _hash(_event_payload(self)):
            raise ValueError("agent_job_event_hash_mismatch")
        return self


class AgentJobAggregate(BaseModel):
    contract: str = AGENT_JOB_REPOSITORY_CONTRACT
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective_ref: str = Field(min_length=1)
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_job_id: str | None = None
    status: AgentJobStatus
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    last_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    last_checkpoint_ref: str | None = None
    recovery_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_aggregate(self) -> AgentJobAggregate:
        _aware(self.created_at, "agent_job_created_at_requires_timezone")
        _aware(self.updated_at, "agent_job_updated_at_requires_timezone")
        if self.updated_at < self.created_at:
            raise ValueError("agent_job_update_predates_create")
        return self


class AgentJobTransition(BaseModel):
    kind: AgentJobEventKind
    occurred_at: datetime
    actor_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    checkpoint_ref: str | None = None
    blocker_codes: tuple[str, ...] = ()


class CreateAgentJobResult(BaseModel):
    aggregate: AgentJobAggregate
    created: bool


class AgentJobPersistence(Protocol):
    """Atomic persistence port; the production adapter is expected to use PostgreSQL.

    ``insert`` must enforce unique ``(tenant_id, requested_by, idempotency_key)``.
    ``append`` must atomically insert the event and update the aggregate only when
    its stored version equals ``expected_version``.
    """

    def find_idempotent(
        self, *, tenant_id: str, requested_by: str, idempotency_key: str
    ) -> AgentJobAggregate | None: ...

    def insert_or_get(
        self, *, aggregate: AgentJobAggregate, created_event: AgentJobEvent
    ) -> tuple[AgentJobAggregate, bool]: ...

    def load(self, *, tenant_id: str, job_id: str) -> AgentJobAggregate | None: ...

    def append(
        self,
        *,
        tenant_id: str,
        job_id: str,
        expected_version: int,
        event: AgentJobEvent,
        aggregate: AgentJobAggregate,
    ) -> AgentJobAggregate: ...

    def list_recoverable(
        self, *, tenant_id: str, updated_before: datetime, limit: int
    ) -> tuple[AgentJobAggregate, ...]: ...

    def list_events(
        self, *, tenant_id: str, job_id: str, after_sequence: int = 0
    ) -> tuple[AgentJobEvent, ...]: ...


def _request_payload(command: AgentJobCreate) -> dict[str, object]:
    return {
        "tenant_id": command.tenant_id,
        "requested_by": command.requested_by,
        "idempotency_key": command.idempotency_key,
        "objective_ref": command.objective_ref,
        "plan_fingerprint": command.plan_fingerprint,
        "parent_job_id": command.parent_job_id,
    }


def _event_payload(event: AgentJobEvent) -> dict[str, object]:
    return {
        "contract": event.contract,
        "event_id": event.event_id,
        "tenant_id": event.tenant_id,
        "job_id": event.job_id,
        "sequence": event.sequence,
        "kind": event.kind.value,
        "occurred_at": event.occurred_at.isoformat(),
        "actor_ref": event.actor_ref,
        "evidence_refs": list(event.evidence_refs),
        "checkpoint_ref": event.checkpoint_ref,
        "blocker_codes": list(event.blocker_codes),
        "previous_event_hash": event.previous_event_hash,
    }


def _build_event(
    *, aggregate: AgentJobAggregate | None, job_id: str, tenant_id: str,
    sequence: int, transition: AgentJobTransition,
) -> AgentJobEvent:
    _aware(transition.occurred_at, "agent_job_event_time_requires_timezone")
    previous = aggregate.last_event_hash if aggregate else GENESIS_EVENT_HASH
    event_id = _hash({"job_id": job_id, "sequence": sequence, "kind": transition.kind.value})
    provisional = AgentJobEvent.model_construct(
        event_id=event_id, tenant_id=tenant_id, job_id=job_id, sequence=sequence,
        kind=transition.kind, occurred_at=transition.occurred_at,
        actor_ref=transition.actor_ref, evidence_refs=transition.evidence_refs,
        checkpoint_ref=transition.checkpoint_ref, blocker_codes=transition.blocker_codes,
        previous_event_hash=previous, event_hash=GENESIS_EVENT_HASH,
    )
    return AgentJobEvent(**provisional.model_dump(exclude={"event_hash"}), event_hash=_hash(_event_payload(provisional)))


def _status_for(kind: AgentJobEventKind) -> AgentJobStatus:
    return {
        AgentJobEventKind.CREATED: AgentJobStatus.QUEUED,
        AgentJobEventKind.STARTED: AgentJobStatus.RUNNING,
        AgentJobEventKind.CHECKPOINTED: AgentJobStatus.RUNNING,
        AgentJobEventKind.RECOVERY_REQUESTED: AgentJobStatus.RECOVERY_REQUIRED,
        AgentJobEventKind.BLOCKED: AgentJobStatus.BLOCKED,
        AgentJobEventKind.COMPLETED: AgentJobStatus.COMPLETED,
        AgentJobEventKind.FAILED: AgentJobStatus.FAILED,
        AgentJobEventKind.CANCELLED: AgentJobStatus.CANCELLED,
    }[kind]


class DurableAgentJobRepository:
    def __init__(self, persistence: AgentJobPersistence):
        self.persistence = persistence

    def create(self, command: AgentJobCreate) -> CreateAgentJobResult:
        command = AgentJobCreate.model_validate(command.model_dump(mode="json"))
        request_fingerprint = _hash(_request_payload(command))
        existing = self.persistence.find_idempotent(
            tenant_id=command.tenant_id, requested_by=command.requested_by,
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise ValueError("agent_job_idempotency_payload_conflict")
            return CreateAgentJobResult(aggregate=existing, created=False)

        job_id = _hash({"request_fingerprint": request_fingerprint})
        transition = AgentJobTransition(
            kind=AgentJobEventKind.CREATED, occurred_at=command.created_at,
            actor_ref=command.requested_by,
        )
        event = _build_event(
            aggregate=None, job_id=job_id, tenant_id=command.tenant_id,
            sequence=1, transition=transition,
        )
        aggregate = AgentJobAggregate(
            job_id=job_id, tenant_id=command.tenant_id, requested_by=command.requested_by,
            idempotency_key=command.idempotency_key, request_fingerprint=request_fingerprint,
            objective_ref=command.objective_ref, plan_fingerprint=command.plan_fingerprint,
            parent_job_id=command.parent_job_id, status=AgentJobStatus.QUEUED, version=1,
            created_at=command.created_at, updated_at=command.created_at,
            last_event_hash=event.event_hash,
        )
        stored, inserted = self.persistence.insert_or_get(
            aggregate=aggregate, created_event=event
        )
        if stored.tenant_id != command.tenant_id:
            raise ValueError("agent_job_persistence_tenant_violation")
        # Closes the lookup/insert race: PostgreSQL may return the row that won the
        # unique-key conflict, but it must be the exact same request.
        if stored.request_fingerprint != request_fingerprint:
            raise ValueError("agent_job_idempotency_payload_conflict")
        return CreateAgentJobResult(aggregate=stored, created=inserted)

    def get(self, *, tenant_id: str, job_id: str) -> AgentJobAggregate:
        value = self.persistence.load(tenant_id=tenant_id, job_id=job_id)
        if value is None:
            raise KeyError("agent_job_not_found")
        if value.tenant_id != tenant_id:
            raise ValueError("agent_job_persistence_tenant_violation")
        return value

    def transition(
        self, *, tenant_id: str, job_id: str, expected_version: int,
        transition: AgentJobTransition,
    ) -> AgentJobAggregate:
        current = self.get(tenant_id=tenant_id, job_id=job_id)
        if current.version != expected_version:
            raise ValueError("agent_job_optimistic_version_conflict")
        if current.status in _TERMINAL:
            raise ValueError("agent_job_terminal_transition_forbidden")
        if transition.occurred_at < current.updated_at:
            raise ValueError("agent_job_event_time_regression")
        if transition.kind is AgentJobEventKind.CREATED:
            raise ValueError("agent_job_duplicate_created_event_forbidden")
        if transition.kind is AgentJobEventKind.CHECKPOINTED and not transition.checkpoint_ref:
            raise ValueError("agent_job_checkpoint_event_requires_checkpoint")
        if transition.kind is AgentJobEventKind.RECOVERY_REQUESTED and not transition.checkpoint_ref:
            raise ValueError("agent_job_recovery_requires_checkpoint")
        if transition.kind is AgentJobEventKind.BLOCKED and not transition.blocker_codes:
            raise ValueError("agent_job_blocked_event_requires_blocker")

        event = _build_event(
            aggregate=current, job_id=job_id, tenant_id=tenant_id,
            sequence=current.version + 1, transition=transition,
        )
        updated = current.model_copy(update={
            "status": _status_for(transition.kind), "version": current.version + 1,
            "updated_at": transition.occurred_at, "last_event_hash": event.event_hash,
            "last_checkpoint_ref": transition.checkpoint_ref or current.last_checkpoint_ref,
            "recovery_count": current.recovery_count + (
                1 if transition.kind is AgentJobEventKind.RECOVERY_REQUESTED else 0
            ),
        })
        updated = AgentJobAggregate.model_validate(updated.model_dump(mode="json"))
        stored = self.persistence.append(
            tenant_id=tenant_id, job_id=job_id, expected_version=expected_version,
            event=event, aggregate=updated,
        )
        if stored.tenant_id != tenant_id:
            raise ValueError("agent_job_persistence_tenant_violation")
        return stored

    def recover_stale(
        self, *, tenant_id: str, updated_before: datetime, recovered_at: datetime,
        actor_ref: str, limit: int = 100,
    ) -> tuple[AgentJobAggregate, ...]:
        _aware(updated_before, "agent_job_recovery_cutoff_requires_timezone")
        _aware(recovered_at, "agent_job_recovery_time_requires_timezone")
        if recovered_at < updated_before:
            raise ValueError("agent_job_recovery_time_predates_cutoff")
        candidates = self.persistence.list_recoverable(
            tenant_id=tenant_id, updated_before=updated_before, limit=limit
        )
        recovered: list[AgentJobAggregate] = []
        for item in candidates:
            if item.tenant_id != tenant_id:
                raise ValueError("agent_job_persistence_tenant_violation")
            if item.status is not AgentJobStatus.RUNNING or not item.last_checkpoint_ref:
                continue
            recovered.append(self.transition(
                tenant_id=tenant_id, job_id=item.job_id, expected_version=item.version,
                transition=AgentJobTransition(
                    kind=AgentJobEventKind.RECOVERY_REQUESTED,
                    occurred_at=recovered_at, actor_ref=actor_ref,
                    checkpoint_ref=item.last_checkpoint_ref,
                    blocker_codes=("agent_job_runtime_restart",),
                ),
            ))
        return tuple(recovered)
