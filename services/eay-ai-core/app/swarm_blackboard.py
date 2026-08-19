"""Append-only shared evidence blackboard for specialist Jarvis colonies.

The blackboard is an index of evidence/artifact references, not a new source of truth.
Workers may publish observations, hypotheses, simulations, blockers and verified-action
references for other colonies to consume, but raw business payloads and credential
material are intentionally excluded from the contract.

Entries are tenant/objective bound, fingerprint sealed, append-only and cutoff aware so
historical replay cannot see evidence that was observed or recorded in the future.
Nothing on the blackboard grants truth or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .swarm_colony_runtime import SwarmColonyTopology
from .swarm_worker_registry import SwarmWorkerRegistry

SWARM_BLACKBOARD_CONTRACT = "eay-swarm-blackboard-v1"


class SwarmBlackboardEntryKind(str, Enum):
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    FINDING = "finding"
    SIMULATION = "simulation"
    DECISION_CANDIDATE = "decision_candidate"
    ACTION_RESULT = "action_result"
    BLOCKER = "blocker"


class SwarmBlackboardEntry(BaseModel):
    contract: str = SWARM_BLACKBOARD_CONTRACT
    entry_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    colony_ref: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    kind: SwarmBlackboardEntryKind
    subject_ref: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    raw_payload_retained: bool = False
    credential_material_retained: bool = False
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def entry_is_secret_safe_and_integral(self) -> "SwarmBlackboardEntry":
        _require_aware(self.observed_at, "swarm_blackboard_observed_at_requires_timezone")
        _require_aware(self.recorded_at, "swarm_blackboard_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("swarm_blackboard_recorded_at_predates_observation")
        if self.raw_payload_retained:
            raise ValueError("swarm_blackboard_raw_payload_forbidden")
        if self.credential_material_retained:
            raise ValueError("swarm_blackboard_credential_material_forbidden")
        if self.truth_authority_granted:
            raise ValueError("swarm_blackboard_never_grants_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("swarm_blackboard_never_grants_execution_authority")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("swarm_blackboard_evidence_refs_must_be_unique")
        for ref in (self.subject_ref, self.artifact_ref, *self.evidence_refs):
            if _looks_secret_bearing(ref):
                raise ValueError("swarm_blackboard_secret_bearing_reference_forbidden")
        expected = _entry_fingerprint(
            _entry_payload_values(
                contract=self.contract,
                entry_id=self.entry_id,
                tenant_id=self.tenant_id,
                objective_ref=self.objective_ref,
                colony_ref=self.colony_ref,
                worker_id=self.worker_id,
                kind=self.kind,
                subject_ref=self.subject_ref,
                artifact_ref=self.artifact_ref,
                evidence_refs=self.evidence_refs,
                observed_at=self.observed_at,
                recorded_at=self.recorded_at,
                confidence=self.confidence,
                raw_payload_retained=self.raw_payload_retained,
                credential_material_retained=self.credential_material_retained,
                truth_authority_granted=self.truth_authority_granted,
                execution_authority_granted=self.execution_authority_granted,
            )
        )
        if self.fingerprint != expected:
            raise ValueError("swarm_blackboard_entry_fingerprint_mismatch")
        return self


class SwarmBlackboardLedger(BaseModel):
    contract: str = SWARM_BLACKBOARD_CONTRACT
    tenant_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    entries: tuple[SwarmBlackboardEntry, ...] = Field(default=(), max_length=4096)
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def ledger_is_bound_and_non_authoritative(self) -> "SwarmBlackboardLedger":
        if self.truth_authority_granted:
            raise ValueError("swarm_blackboard_ledger_never_grants_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("swarm_blackboard_ledger_never_grants_execution_authority")
        if any(item.tenant_id != self.tenant_id for item in self.entries):
            raise ValueError("swarm_blackboard_cross_tenant_entry_forbidden")
        if any(item.objective_ref != self.objective_ref for item in self.entries):
            raise ValueError("swarm_blackboard_cross_objective_entry_forbidden")
        by_id: dict[str, str] = {}
        for item in self.entries:
            existing = by_id.get(item.entry_id)
            if existing is not None and existing != item.fingerprint:
                raise ValueError("swarm_blackboard_entry_id_conflict")
            by_id[item.entry_id] = item.fingerprint
        return self


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _looks_secret_bearing(value: str) -> bool:
    lowered = value.lower()
    markers = (
        "authorization=",
        "bearer ",
        "password=",
        "passwd=",
        "token=",
        "api_key=",
        "apikey=",
        "cookie=",
        "x-goog-signature=",
        "x-amz-signature=",
        "sig=",
    )
    return any(marker in lowered for marker in markers)


def _entry_payload_values(
    *,
    contract: str,
    entry_id: str,
    tenant_id: str,
    objective_ref: str,
    colony_ref: str,
    worker_id: str,
    kind: SwarmBlackboardEntryKind | str,
    subject_ref: str,
    artifact_ref: str,
    evidence_refs: tuple[str, ...] | list[str],
    observed_at: datetime,
    recorded_at: datetime,
    confidence: float,
    raw_payload_retained: bool,
    credential_material_retained: bool,
    truth_authority_granted: bool,
    execution_authority_granted: bool,
) -> dict:
    """Canonical fingerprint payload shared by construction and validation."""

    return {
        "contract": str(contract),
        "entry_id": str(entry_id),
        "tenant_id": str(tenant_id),
        "objective_ref": str(objective_ref),
        "colony_ref": str(colony_ref),
        "worker_id": str(worker_id),
        "kind": kind.value if isinstance(kind, SwarmBlackboardEntryKind) else str(kind),
        "subject_ref": str(subject_ref),
        "artifact_ref": str(artifact_ref),
        "evidence_refs": [str(item) for item in evidence_refs],
        "observed_at": observed_at.isoformat(),
        "recorded_at": recorded_at.isoformat(),
        "confidence": float(confidence),
        "raw_payload_retained": bool(raw_payload_retained),
        "credential_material_retained": bool(credential_material_retained),
        "truth_authority_granted": bool(truth_authority_granted),
        "execution_authority_granted": bool(execution_authority_granted),
    }


def _entry_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_blackboard_entry(
    *,
    entry_id: str,
    tenant_id: str,
    objective_ref: str,
    colony_ref: str,
    worker_id: str,
    kind: SwarmBlackboardEntryKind,
    subject_ref: str,
    artifact_ref: str,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    confidence: float,
) -> SwarmBlackboardEntry:
    """Create a sealed reference-only blackboard entry."""

    _require_aware(observed_at, "swarm_blackboard_observed_at_requires_timezone")
    _require_aware(recorded_at, "swarm_blackboard_recorded_at_requires_timezone")
    payload = _entry_payload_values(
        contract=SWARM_BLACKBOARD_CONTRACT,
        entry_id=entry_id,
        tenant_id=tenant_id,
        objective_ref=objective_ref,
        colony_ref=colony_ref,
        worker_id=worker_id,
        kind=kind,
        subject_ref=subject_ref,
        artifact_ref=artifact_ref,
        evidence_refs=evidence_refs,
        observed_at=observed_at,
        recorded_at=recorded_at,
        confidence=confidence,
        raw_payload_retained=False,
        credential_material_retained=False,
        truth_authority_granted=False,
        execution_authority_granted=False,
    )
    return SwarmBlackboardEntry.model_validate(
        {**payload, "fingerprint": _entry_fingerprint(payload)}
    )


def _worker_colony_ref(
    *,
    worker_id: str,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
) -> str:
    workers = [item for item in registry.workers if item.worker_id == worker_id]
    if len(workers) != 1:
        raise ValueError("swarm_blackboard_worker_not_registered")
    worker = workers[0]
    if registry.tenant_id != topology.tenant_id or worker.tenant_id != topology.tenant_id:
        raise ValueError("swarm_blackboard_worker_topology_tenant_mismatch")
    matches = [
        colony.colony_ref
        for colony in topology.colonies
        if worker.worker_class in colony.worker_classes
    ]
    if len(matches) != 1:
        raise ValueError("swarm_blackboard_worker_colony_unresolved")
    return matches[0]


def append_blackboard_entry(
    *,
    ledger: SwarmBlackboardLedger,
    entry: SwarmBlackboardEntry,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
) -> SwarmBlackboardLedger:
    """Append one exact worker-produced entry; exact retry is idempotent."""

    ledger = SwarmBlackboardLedger.model_validate(ledger.model_dump(mode="json"))
    entry = SwarmBlackboardEntry.model_validate(entry.model_dump(mode="json"))
    if entry.tenant_id != ledger.tenant_id or registry.tenant_id != ledger.tenant_id:
        raise ValueError("swarm_blackboard_append_tenant_mismatch")
    if entry.objective_ref != ledger.objective_ref:
        raise ValueError("swarm_blackboard_append_objective_mismatch")
    expected_colony = _worker_colony_ref(
        worker_id=entry.worker_id,
        registry=registry,
        topology=topology,
    )
    if entry.colony_ref != expected_colony:
        raise ValueError("swarm_blackboard_producer_colony_mismatch")

    for existing in ledger.entries:
        if existing.entry_id != entry.entry_id:
            continue
        if existing.fingerprint == entry.fingerprint:
            return ledger
        raise ValueError("swarm_blackboard_entry_id_conflict")
    if len(ledger.entries) >= 4096:
        raise ValueError("swarm_blackboard_capacity_exhausted")
    return SwarmBlackboardLedger(
        tenant_id=ledger.tenant_id,
        objective_ref=ledger.objective_ref,
        entries=(*ledger.entries, entry),
    )


def visible_blackboard_entries(
    *,
    ledger: SwarmBlackboardLedger,
    as_of: datetime,
    colony_refs: tuple[str, ...] | None = None,
    kinds: tuple[SwarmBlackboardEntryKind, ...] | None = None,
) -> tuple[SwarmBlackboardEntry, ...]:
    """Return only evidence that both happened and was recorded by the replay cutoff."""

    ledger = SwarmBlackboardLedger.model_validate(ledger.model_dump(mode="json"))
    _require_aware(as_of, "swarm_blackboard_as_of_requires_timezone")
    allowed_colonies = set(colony_refs or ())
    allowed_kinds = set(kinds or ())
    visible = [
        item
        for item in ledger.entries
        if item.observed_at <= as_of
        and item.recorded_at <= as_of
        and (not allowed_colonies or item.colony_ref in allowed_colonies)
        and (not allowed_kinds or item.kind in allowed_kinds)
    ]
    return tuple(sorted(visible, key=lambda item: (item.recorded_at, item.entry_id)))
