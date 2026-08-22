from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agent_job_repository import (
    AgentJobAggregate,
    AgentJobCreate,
    AgentJobEvent,
    AgentJobEventKind,
    AgentJobStatus,
    AgentJobTransition,
    DurableAgentJobRepository,
)

NOW = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
PLAN = "a" * 64


class ContractPersistence:
    """Test double for the atomic PostgreSQL persistence port, not product storage."""

    def __init__(self) -> None:
        self.aggregates: dict[tuple[str, str], AgentJobAggregate] = {}
        self.idempotency: dict[tuple[str, str, str], str] = {}
        self.events: dict[tuple[str, str], list[AgentJobEvent]] = {}

    def find_idempotent(self, *, tenant_id, requested_by, idempotency_key):
        job_id = self.idempotency.get((tenant_id, requested_by, idempotency_key))
        return self.aggregates.get((tenant_id, job_id)) if job_id else None

    def insert_or_get(self, *, aggregate, created_event):
        idem = (aggregate.tenant_id, aggregate.requested_by, aggregate.idempotency_key)
        if idem in self.idempotency:
            stored_id = self.idempotency[idem]
            return self.aggregates[(aggregate.tenant_id, stored_id)], False
        self.idempotency[idem] = aggregate.job_id
        self.aggregates[(aggregate.tenant_id, aggregate.job_id)] = aggregate
        self.events[(aggregate.tenant_id, aggregate.job_id)] = [created_event]
        return aggregate, True

    def load(self, *, tenant_id, job_id):
        return self.aggregates.get((tenant_id, job_id))

    def append(self, *, tenant_id, job_id, expected_version, event, aggregate):
        current = self.aggregates.get((tenant_id, job_id))
        if current is None:
            raise KeyError("agent_job_not_found")
        if current.version != expected_version:
            raise ValueError("agent_job_optimistic_version_conflict")
        self.events[(tenant_id, job_id)].append(event)
        self.aggregates[(tenant_id, job_id)] = aggregate
        return aggregate

    def list_recoverable(self, *, tenant_id, updated_before, limit):
        return tuple(
            item
            for (stored_tenant, _), item in self.aggregates.items()
            if stored_tenant == tenant_id and item.updated_at <= updated_before
        )[:limit]

    def list_events(self, *, tenant_id, job_id, after_sequence=0):
        return tuple(
            item for item in self.events.get((tenant_id, job_id), [])
            if item.sequence > after_sequence
        )


def command(**updates) -> AgentJobCreate:
    values = {
        "tenant_id": "tenant-a",
        "requested_by": "user://erdi",
        "idempotency_key": "hire-agents-0001",
        "objective_ref": "objective://jarvis-research",
        "plan_fingerprint": PLAN,
        "created_at": NOW,
    }
    values.update(updates)
    return AgentJobCreate(**values)


def test_create_is_idempotent_and_payload_drift_fails_closed() -> None:
    storage = ContractPersistence()
    repository = DurableAgentJobRepository(storage)

    first = repository.create(command())
    replay = repository.create(command())

    assert first.created is True
    assert replay.created is False
    assert replay.aggregate == first.aggregate
    assert len(storage.list_events(
        tenant_id="tenant-a", job_id=first.aggregate.job_id
    )) == 1

    with pytest.raises(ValueError, match="agent_job_idempotency_payload_conflict"):
        repository.create(command(objective_ref="objective://different"))


def test_tenant_isolation_hides_job_and_scopes_same_idempotency_key() -> None:
    storage = ContractPersistence()
    repository = DurableAgentJobRepository(storage)
    tenant_a = repository.create(command()).aggregate
    tenant_b = repository.create(command(tenant_id="tenant-b")).aggregate

    assert tenant_a.job_id != tenant_b.job_id
    with pytest.raises(KeyError, match="agent_job_not_found"):
        repository.get(tenant_id="tenant-b", job_id=tenant_a.job_id)


def test_append_only_ledger_is_hash_chained_and_version_guarded() -> None:
    storage = ContractPersistence()
    repository = DurableAgentJobRepository(storage)
    created = repository.create(command()).aggregate
    started = repository.transition(
        tenant_id="tenant-a",
        job_id=created.job_id,
        expected_version=1,
        transition=AgentJobTransition(
            kind=AgentJobEventKind.STARTED,
            occurred_at=NOW + timedelta(seconds=1),
            actor_ref="runtime://scheduler",
        ),
    )
    checkpointed = repository.transition(
        tenant_id="tenant-a",
        job_id=created.job_id,
        expected_version=2,
        transition=AgentJobTransition(
            kind=AgentJobEventKind.CHECKPOINTED,
            occurred_at=NOW + timedelta(seconds=2),
            actor_ref="worker://research-1",
            checkpoint_ref="checkpoint://sha256-1",
            evidence_refs=("evidence://result-1",),
        ),
    )

    events = storage.list_events(tenant_id="tenant-a", job_id=created.job_id)
    assert checkpointed.version == 3
    assert checkpointed.status is AgentJobStatus.RUNNING
    assert events[1].previous_event_hash == events[0].event_hash
    assert events[2].previous_event_hash == events[1].event_hash
    assert checkpointed.last_event_hash == events[-1].event_hash
    with pytest.raises(ValueError, match="agent_job_optimistic_version_conflict"):
        repository.transition(
            tenant_id="tenant-a", job_id=created.job_id, expected_version=started.version,
            transition=AgentJobTransition(
                kind=AgentJobEventKind.BLOCKED,
                occurred_at=NOW + timedelta(seconds=3),
                actor_ref="runtime://scheduler",
                blocker_codes=("stale-writer",),
            ),
        )


def test_restart_recovery_requires_durable_checkpoint_and_is_tenant_bound() -> None:
    storage = ContractPersistence()
    repository = DurableAgentJobRepository(storage)
    recoverable = repository.create(command()).aggregate
    recoverable = repository.transition(
        tenant_id="tenant-a", job_id=recoverable.job_id, expected_version=1,
        transition=AgentJobTransition(
            kind=AgentJobEventKind.STARTED, occurred_at=NOW + timedelta(seconds=1),
            actor_ref="runtime://scheduler",
        ),
    )
    recoverable = repository.transition(
        tenant_id="tenant-a", job_id=recoverable.job_id, expected_version=2,
        transition=AgentJobTransition(
            kind=AgentJobEventKind.CHECKPOINTED,
            occurred_at=NOW + timedelta(seconds=2), actor_ref="worker://one",
            checkpoint_ref="checkpoint://durable-1",
        ),
    )
    repository.create(command(
        tenant_id="tenant-b", idempotency_key="hire-agents-0002"
    ))

    recovered = repository.recover_stale(
        tenant_id="tenant-a",
        updated_before=NOW + timedelta(minutes=1),
        recovered_at=NOW + timedelta(minutes=2),
        actor_ref="runtime://restart-reconciler",
    )

    assert len(recovered) == 1
    assert recovered[0].job_id == recoverable.job_id
    assert recovered[0].status is AgentJobStatus.RECOVERY_REQUIRED
    assert recovered[0].recovery_count == 1
    assert recovered[0].last_checkpoint_ref == "checkpoint://durable-1"
    assert storage.load(tenant_id="tenant-b", job_id=recoverable.job_id) is None


def test_terminal_job_cannot_be_reopened() -> None:
    storage = ContractPersistence()
    repository = DurableAgentJobRepository(storage)
    created = repository.create(command()).aggregate
    completed = repository.transition(
        tenant_id="tenant-a", job_id=created.job_id, expected_version=1,
        transition=AgentJobTransition(
            kind=AgentJobEventKind.COMPLETED,
            occurred_at=NOW + timedelta(seconds=1), actor_ref="runtime://scheduler",
            evidence_refs=("evidence://final",),
        ),
    )
    with pytest.raises(ValueError, match="agent_job_terminal_transition_forbidden"):
        repository.transition(
            tenant_id="tenant-a", job_id=created.job_id,
            expected_version=completed.version,
            transition=AgentJobTransition(
                kind=AgentJobEventKind.STARTED,
                occurred_at=NOW + timedelta(seconds=2), actor_ref="runtime://scheduler",
            ),
        )
