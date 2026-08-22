"""Durable, append-only evidence ledger for Jarvis swarm worker routing.

The ledger persists only already-governed WorkerTaskOutcomeEvidence. It adds a
recorded-at boundary so historical routing cannot see evidence that Jarvis had
not ingested yet. The ledger never grants worker eligibility or execution
authority; all routing continues through the canonical worker router.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .parallel_mission_orchestration import ParallelMissionLane
from .parallel_mission_scheduler import ParallelLaneSchedulingProfile
from .swarm_worker_registry import SwarmLaneRequirement, SwarmWorkerRegistry
from .worker_task_routing import (
    WorkerTaskOutcomeEvidence,
    WorkerTaskRoutingPolicy,
    WorkerTaskRoutingPreference,
    routing_preferences_for_plan,
)

WORKER_OUTCOME_EVIDENCE_LEDGER_CONTRACT = "eay-worker-outcome-evidence-ledger-v1"

_FORBIDDEN_REFERENCE_MARKERS = (
    "authorization=",
    "bearer ",
    "token=",
    "access_token=",
    "refresh_token=",
    "api_key=",
    "apikey=",
    "password=",
    "passwd=",
    "x-amz-signature=",
)


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ensure_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _evidence_identity(outcome: WorkerTaskOutcomeEvidence) -> str:
    return _canonical_hash(
        {
            "tenant_id": outcome.tenant_id,
            "worker_id": outcome.worker_id,
            "scheduling_class": outcome.scheduling_class.value,
            "capability_ref": outcome.capability_ref,
            "observed_at": outcome.observed_at.isoformat(),
            "evidence_refs": sorted(outcome.evidence_refs),
        }
    )


def _entry_payload(entry: "WorkerOutcomeLedgerEntry") -> dict[str, object]:
    return {
        "contract": entry.contract,
        "entry_id": entry.entry_id,
        "tenant_id": entry.tenant_id,
        "recorded_at": entry.recorded_at.isoformat(),
        "outcome": entry.outcome.model_dump(mode="json"),
        "truth_authority_granted": False,
        "execution_authority_granted": False,
    }


class WorkerOutcomeLedgerEntry(BaseModel):
    contract: str = WORKER_OUTCOME_EVIDENCE_LEDGER_CONTRACT
    entry_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1)
    recorded_at: datetime
    outcome: WorkerTaskOutcomeEvidence
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def entry_is_integrity_bound(self) -> "WorkerOutcomeLedgerEntry":
        _ensure_aware(self.recorded_at, "worker_outcome_ledger_recorded_at_requires_timezone")
        if self.outcome.tenant_id != self.tenant_id:
            raise ValueError("worker_outcome_ledger_entry_tenant_mismatch")
        if self.recorded_at < self.outcome.observed_at:
            raise ValueError("worker_outcome_ledger_recording_precedes_observation")
        if self.truth_authority_granted or self.execution_authority_granted:
            raise ValueError("worker_outcome_ledger_never_grants_authority")
        folded_refs = tuple(ref.casefold() for ref in self.outcome.evidence_refs)
        if any(
            marker in ref
            for ref in folded_refs
            for marker in _FORBIDDEN_REFERENCE_MARKERS
        ):
            raise ValueError("worker_outcome_ledger_reference_may_contain_secret")
        if self.entry_id != _evidence_identity(self.outcome):
            raise ValueError("worker_outcome_ledger_entry_identity_mismatch")
        if self.fingerprint != _canonical_hash(_entry_payload(self)):
            raise ValueError("worker_outcome_ledger_entry_fingerprint_mismatch")
        return self


def _ledger_payload(ledger: "WorkerOutcomeEvidenceLedger") -> dict[str, object]:
    return {
        "contract": ledger.contract,
        "tenant_id": ledger.tenant_id,
        "created_at": ledger.created_at.isoformat(),
        "updated_at": ledger.updated_at.isoformat(),
        "entry_fingerprints": [item.fingerprint for item in ledger.entries],
        "truth_authority_granted": False,
        "execution_authority_granted": False,
        "automatic_policy_update_allowed": False,
        "automatic_model_weight_update_allowed": False,
    }


class WorkerOutcomeEvidenceLedger(BaseModel):
    contract: str = WORKER_OUTCOME_EVIDENCE_LEDGER_CONTRACT
    tenant_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    entries: tuple[WorkerOutcomeLedgerEntry, ...] = Field(default=(), max_length=10_000)
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    automatic_policy_update_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def ledger_is_integrity_bound_and_non_authoritative(self) -> "WorkerOutcomeEvidenceLedger":
        _ensure_aware(self.created_at, "worker_outcome_ledger_created_at_requires_timezone")
        _ensure_aware(self.updated_at, "worker_outcome_ledger_updated_at_requires_timezone")
        if self.updated_at < self.created_at:
            raise ValueError("worker_outcome_ledger_updated_before_creation")
        if any(item.tenant_id != self.tenant_id for item in self.entries):
            raise ValueError("worker_outcome_ledger_cross_tenant_entry_forbidden")
        entry_ids = [item.entry_id for item in self.entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("worker_outcome_ledger_entry_ids_must_be_unique")
        if tuple(sorted(self.entries, key=lambda item: (item.recorded_at, item.entry_id))) != self.entries:
            raise ValueError("worker_outcome_ledger_entries_must_be_canonical_order")
        if (
            self.truth_authority_granted
            or self.execution_authority_granted
            or self.automatic_policy_update_allowed
            or self.automatic_model_weight_update_allowed
        ):
            raise ValueError("worker_outcome_ledger_never_grants_or_self_modifies")
        if self.fingerprint != _canonical_hash(_ledger_payload(self)):
            raise ValueError("worker_outcome_ledger_fingerprint_mismatch")
        return self


def _build_ledger(
    *,
    tenant_id: str,
    created_at: datetime,
    updated_at: datetime,
    entries: tuple[WorkerOutcomeLedgerEntry, ...],
) -> WorkerOutcomeEvidenceLedger:
    provisional = WorkerOutcomeEvidenceLedger.model_construct(
        contract=WORKER_OUTCOME_EVIDENCE_LEDGER_CONTRACT,
        tenant_id=tenant_id,
        created_at=created_at,
        updated_at=updated_at,
        entries=entries,
        truth_authority_granted=False,
        execution_authority_granted=False,
        automatic_policy_update_allowed=False,
        automatic_model_weight_update_allowed=False,
        fingerprint="0" * 64,
    )
    return WorkerOutcomeEvidenceLedger(
        tenant_id=tenant_id,
        created_at=created_at,
        updated_at=updated_at,
        entries=entries,
        fingerprint=_canonical_hash(_ledger_payload(provisional)),
    )


def new_worker_outcome_evidence_ledger(
    *, tenant_id: str, created_at: datetime
) -> WorkerOutcomeEvidenceLedger:
    _ensure_aware(created_at, "worker_outcome_ledger_created_at_requires_timezone")
    return _build_ledger(
        tenant_id=tenant_id,
        created_at=created_at,
        updated_at=created_at,
        entries=(),
    )


def _build_entry(
    *, outcome: WorkerTaskOutcomeEvidence, recorded_at: datetime
) -> WorkerOutcomeLedgerEntry:
    entry_id = _evidence_identity(outcome)
    provisional = WorkerOutcomeLedgerEntry.model_construct(
        contract=WORKER_OUTCOME_EVIDENCE_LEDGER_CONTRACT,
        entry_id=entry_id,
        tenant_id=outcome.tenant_id,
        recorded_at=recorded_at,
        outcome=outcome,
        truth_authority_granted=False,
        execution_authority_granted=False,
        fingerprint="0" * 64,
    )
    return WorkerOutcomeLedgerEntry(
        entry_id=entry_id,
        tenant_id=outcome.tenant_id,
        recorded_at=recorded_at,
        outcome=outcome,
        fingerprint=_canonical_hash(_entry_payload(provisional)),
    )


def append_worker_outcome_evidence(
    *,
    ledger: WorkerOutcomeEvidenceLedger,
    outcome: WorkerTaskOutcomeEvidence,
    recorded_at: datetime,
) -> WorkerOutcomeEvidenceLedger:
    """Append one immutable outcome; exact retries are idempotent."""

    ledger = WorkerOutcomeEvidenceLedger.model_validate(ledger.model_dump(mode="json"))
    outcome = WorkerTaskOutcomeEvidence.model_validate(outcome.model_dump(mode="json"))
    _ensure_aware(recorded_at, "worker_outcome_ledger_recorded_at_requires_timezone")
    if outcome.tenant_id != ledger.tenant_id:
        raise ValueError("worker_outcome_ledger_cross_tenant_append_forbidden")
    if recorded_at < ledger.updated_at:
        raise ValueError("worker_outcome_ledger_recorded_at_regression")

    entry_id = _evidence_identity(outcome)
    existing = next((item for item in ledger.entries if item.entry_id == entry_id), None)
    if existing is not None:
        if existing.outcome.model_dump(mode="json") != outcome.model_dump(mode="json"):
            raise ValueError("worker_outcome_ledger_evidence_identity_conflict")
        return ledger

    entry = _build_entry(outcome=outcome, recorded_at=recorded_at)
    entries = tuple(sorted((*ledger.entries, entry), key=lambda item: (item.recorded_at, item.entry_id)))
    return _build_ledger(
        tenant_id=ledger.tenant_id,
        created_at=ledger.created_at,
        updated_at=recorded_at,
        entries=entries,
    )


def worker_outcomes_known_as_of(
    *, ledger: WorkerOutcomeEvidenceLedger, as_of: datetime
) -> tuple[WorkerTaskOutcomeEvidence, ...]:
    """Return only evidence observed and recorded by the historical cutoff."""

    ledger = WorkerOutcomeEvidenceLedger.model_validate(ledger.model_dump(mode="json"))
    _ensure_aware(as_of, "worker_outcome_ledger_as_of_requires_timezone")
    return tuple(
        item.outcome
        for item in ledger.entries
        if item.recorded_at <= as_of and item.outcome.observed_at <= as_of
    )


def routing_preferences_from_worker_ledger(
    *,
    ledger: WorkerOutcomeEvidenceLedger,
    registry: SwarmWorkerRegistry,
    lanes: tuple[ParallelMissionLane, ...],
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    requirements: Mapping[str, SwarmLaneRequirement],
    as_of: datetime,
    policy: WorkerTaskRoutingPolicy | None = None,
) -> dict[str, WorkerTaskRoutingPreference]:
    """Refresh normal canonical routing preferences from historical ledger evidence."""

    if ledger.tenant_id != registry.tenant_id:
        raise ValueError("worker_outcome_ledger_registry_tenant_mismatch")
    outcomes = worker_outcomes_known_as_of(ledger=ledger, as_of=as_of)
    return routing_preferences_for_plan(
        registry=registry,
        lanes=lanes,
        profiles=dict(profiles),
        requirements=dict(requirements),
        outcomes=outcomes,
        now=as_of,
        policy=policy,
    )
