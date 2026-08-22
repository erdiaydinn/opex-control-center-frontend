"""Lane-level global resource leases for Jarvis multi-objective swarms.

The older global objective arbiter conservatively serializes an entire objective when
one pending write conflicts. This broker narrows that lock to the exact mutating lane.
Independent read/research/simulation lanes from both objectives may keep running.

Lease expiry is intentionally *not* an automatic unlock. A timed-out worker may still
have committed a side effect. Stale leases therefore keep blocking until explicit
reconciliation proves VERIFIED_EFFECT, RECONCILED_NO_EFFECT or NO_SIDE_EFFECT_ATTEMPTED.
The broker is concurrency control only and never grants business execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .global_objective_arbiter import GlobalObjectiveCandidate
from .parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan

GLOBAL_LANE_LEASE_BROKER_CONTRACT = "eay-global-lane-lease-broker-v1"


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


class LaneLeaseReleaseDisposition(str, Enum):
    VERIFIED_EFFECT = "verified_effect"
    RECONCILED_NO_EFFECT = "reconciled_no_effect"
    NO_SIDE_EFFECT_ATTEMPTED = "no_side_effect_attempted"


class GlobalLaneLease(BaseModel):
    contract: str = GLOBAL_LANE_LEASE_BROKER_CONTRACT
    lease_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    lane_id: str = Field(min_length=1)
    resource_refs: tuple[str, ...] = Field(min_length=1)
    idempotency_keys: tuple[str, ...] = ()
    acquired_at: datetime
    expires_at: datetime
    released_at: datetime | None = None
    release_disposition: LaneLeaseReleaseDisposition | None = None
    release_evidence_refs: tuple[str, ...] = ()
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def lease_is_integrity_bound_and_non_authoritative(self) -> "GlobalLaneLease":
        _aware(self.acquired_at, "global_lane_lease_acquired_at_requires_timezone")
        _aware(self.expires_at, "global_lane_lease_expires_at_requires_timezone")
        if self.expires_at <= self.acquired_at:
            raise ValueError("global_lane_lease_expiry_must_follow_acquisition")
        if len(self.resource_refs) != len(set(self.resource_refs)):
            raise ValueError("global_lane_lease_resource_refs_must_be_unique")
        if len(self.idempotency_keys) != len(set(self.idempotency_keys)):
            raise ValueError("global_lane_lease_idempotency_keys_must_be_unique")
        if self.execution_authority_granted:
            raise ValueError("global_lane_lease_never_grants_execution_authority")
        if self.released_at is None:
            if self.release_disposition is not None or self.release_evidence_refs:
                raise ValueError("global_lane_lease_release_fields_without_release")
        else:
            _aware(self.released_at, "global_lane_lease_released_at_requires_timezone")
            if self.released_at < self.acquired_at:
                raise ValueError("global_lane_lease_release_precedes_acquisition")
            if self.release_disposition is None or not self.release_evidence_refs:
                raise ValueError("global_lane_lease_release_requires_disposition_and_evidence")
        if self.fingerprint != _hash(_lease_payload(self)):
            raise ValueError("global_lane_lease_fingerprint_mismatch")
        return self

    def blocks_at(self, now: datetime) -> bool:
        _aware(now, "global_lane_lease_now_requires_timezone")
        return self.released_at is None

    def stale_at(self, now: datetime) -> bool:
        _aware(now, "global_lane_lease_now_requires_timezone")
        return self.released_at is None and self.expires_at <= now


def _lease_payload(lease: GlobalLaneLease) -> dict[str, object]:
    return {
        "contract": lease.contract,
        "lease_id": lease.lease_id,
        "tenant_id": lease.tenant_id,
        "objective_ref": lease.objective_ref,
        "lane_id": lease.lane_id,
        "resource_refs": list(lease.resource_refs),
        "idempotency_keys": list(lease.idempotency_keys),
        "acquired_at": lease.acquired_at.isoformat(),
        "expires_at": lease.expires_at.isoformat(),
        "released_at": lease.released_at.isoformat() if lease.released_at else None,
        "release_disposition": lease.release_disposition.value if lease.release_disposition else None,
        "release_evidence_refs": list(lease.release_evidence_refs),
        "execution_authority_granted": False,
    }


def _lease_id(
    *,
    tenant_id: str,
    objective_ref: str,
    lane_id: str,
    resource_refs: tuple[str, ...],
    idempotency_keys: tuple[str, ...],
    acquired_at: datetime,
) -> str:
    return _hash(
        {
            "tenant_id": tenant_id,
            "objective_ref": objective_ref,
            "lane_id": lane_id,
            "resource_refs": list(resource_refs),
            "idempotency_keys": list(idempotency_keys),
            "acquired_at": acquired_at.isoformat(),
        }
    )


def _build_lease(
    *,
    tenant_id: str,
    objective_ref: str,
    lane_id: str,
    resource_refs: tuple[str, ...],
    idempotency_keys: tuple[str, ...],
    acquired_at: datetime,
    expires_at: datetime,
    released_at: datetime | None = None,
    release_disposition: LaneLeaseReleaseDisposition | None = None,
    release_evidence_refs: tuple[str, ...] = (),
) -> GlobalLaneLease:
    lease_id = _lease_id(
        tenant_id=tenant_id,
        objective_ref=objective_ref,
        lane_id=lane_id,
        resource_refs=resource_refs,
        idempotency_keys=idempotency_keys,
        acquired_at=acquired_at,
    )
    provisional = GlobalLaneLease.model_construct(
        contract=GLOBAL_LANE_LEASE_BROKER_CONTRACT,
        lease_id=lease_id,
        tenant_id=tenant_id,
        objective_ref=objective_ref,
        lane_id=lane_id,
        resource_refs=resource_refs,
        idempotency_keys=idempotency_keys,
        acquired_at=acquired_at,
        expires_at=expires_at,
        released_at=released_at,
        release_disposition=release_disposition,
        release_evidence_refs=release_evidence_refs,
        execution_authority_granted=False,
        fingerprint="0" * 64,
    )
    return GlobalLaneLease(
        lease_id=lease_id,
        tenant_id=tenant_id,
        objective_ref=objective_ref,
        lane_id=lane_id,
        resource_refs=resource_refs,
        idempotency_keys=idempotency_keys,
        acquired_at=acquired_at,
        expires_at=expires_at,
        released_at=released_at,
        release_disposition=release_disposition,
        release_evidence_refs=release_evidence_refs,
        fingerprint=_hash(_lease_payload(provisional)),
    )


def release_global_lane_lease(
    *,
    lease: GlobalLaneLease,
    released_at: datetime,
    disposition: LaneLeaseReleaseDisposition,
    evidence_refs: tuple[str, ...],
) -> GlobalLaneLease:
    """Explicitly release a lease only with reconciliation/effect evidence."""

    lease = GlobalLaneLease.model_validate(lease.model_dump(mode="json"))
    _aware(released_at, "global_lane_lease_released_at_requires_timezone")
    if lease.released_at is not None:
        if (
            lease.released_at == released_at
            and lease.release_disposition is disposition
            and lease.release_evidence_refs == evidence_refs
        ):
            return lease
        raise ValueError("global_lane_lease_already_released")
    if not evidence_refs or len(evidence_refs) != len(set(evidence_refs)):
        raise ValueError("global_lane_lease_release_requires_unique_evidence")
    return _build_lease(
        tenant_id=lease.tenant_id,
        objective_ref=lease.objective_ref,
        lane_id=lease.lane_id,
        resource_refs=lease.resource_refs,
        idempotency_keys=lease.idempotency_keys,
        acquired_at=lease.acquired_at,
        expires_at=lease.expires_at,
        released_at=released_at,
        release_disposition=disposition,
        release_evidence_refs=evidence_refs,
    )


class GlobalLaneLeasePolicy(BaseModel):
    contract: str = GLOBAL_LANE_LEASE_BROKER_CONTRACT
    max_selected_lanes: int = Field(default=512, ge=1, le=2_048)
    lease_ttl_seconds: int = Field(default=300, ge=30, le=86_400)


class GlobalLaneSelection(BaseModel):
    objective_ref: str
    tenant_id: str
    lane_id: str
    mutating: bool
    lease_id: str | None = None
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def selection_is_consistent(self) -> "GlobalLaneSelection":
        if self.execution_authority_granted:
            raise ValueError("global_lane_selection_never_grants_execution_authority")
        if self.mutating != (self.lease_id is not None):
            raise ValueError("global_lane_selection_mutation_lease_mismatch")
        return self


class GlobalLaneLeaseAdmission(BaseModel):
    contract: str = GLOBAL_LANE_LEASE_BROKER_CONTRACT
    selected: tuple[GlobalLaneSelection, ...]
    deferred: dict[str, tuple[str, ...]]
    issued_leases: tuple[GlobalLaneLease, ...]
    blocking_stale_lease_ids: tuple[str, ...] = ()
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def admission_is_non_authoritative(self) -> "GlobalLaneLeaseAdmission":
        if self.execution_authority_granted:
            raise ValueError("global_lane_lease_admission_never_grants_execution_authority")
        keys = [f"{item.objective_ref}::{item.lane_id}" for item in self.selected]
        if len(keys) != len(set(keys)):
            raise ValueError("global_lane_lease_selected_lane_refs_must_be_unique")
        if set(keys) & set(self.deferred):
            raise ValueError("global_lane_lease_selected_deferred_overlap")
        lease_ids = [item.lease_id for item in self.issued_leases]
        if len(lease_ids) != len(set(lease_ids)):
            raise ValueError("global_lane_lease_issued_ids_must_be_unique")
        return self


def _lane_key(objective_ref: str, lane_id: str) -> str:
    return f"{objective_ref}::{lane_id}"


def _lane_ranking(
    candidate: GlobalObjectiveCandidate,
    lane: ParallelMissionLane,
) -> tuple[int, float, int, int, str, str]:
    if candidate.deadline_at is None:
        return (1, float("inf"), -candidate.priority, -lane.priority, candidate.objective_ref, lane.lane_id)
    return (
        0,
        candidate.deadline_at.timestamp(),
        -candidate.priority,
        -lane.priority,
        candidate.objective_ref,
        lane.lane_id,
    )


def _claim(lane: ParallelMissionLane) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not lane.has_pending_side_effect():
        return (), ()
    return (
        tuple(sorted(lane.exclusive_resource_refs)),
        tuple(sorted(lane.pending_idempotency_keys())),
    )


def _lease_conflicts(
    *,
    tenant_id: str,
    resources: tuple[str, ...],
    idempotency_keys: tuple[str, ...],
    leases: tuple[GlobalLaneLease, ...],
    now: datetime,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    blockers: list[str] = []
    stale_ids: list[str] = []
    resource_set = set(resources)
    key_set = set(idempotency_keys)
    for lease in leases:
        if lease.tenant_id != tenant_id or not lease.blocks_at(now):
            continue
        shared_resources = resource_set & set(lease.resource_refs)
        shared_keys = key_set & set(lease.idempotency_keys)
        if not shared_resources and not shared_keys:
            continue
        if lease.stale_at(now):
            blockers.append("global_lane_stale_lease_requires_reconciliation")
            stale_ids.append(lease.lease_id)
        if shared_resources:
            blockers.append("global_lane_resource_lease_conflict")
        if shared_keys:
            blockers.append("global_lane_idempotency_lease_conflict")
    return tuple(dict.fromkeys(blockers)), tuple(dict.fromkeys(stale_ids))


def admit_global_lane_leases(
    *,
    candidates: tuple[GlobalObjectiveCandidate, ...],
    active_leases: tuple[GlobalLaneLease, ...],
    now: datetime,
    policy: GlobalLaneLeasePolicy | None = None,
) -> GlobalLaneLeaseAdmission:
    """Admit safe lanes across objectives and issue leases only for pending writes."""

    _aware(now, "global_lane_lease_now_requires_timezone")
    rules = policy or GlobalLaneLeasePolicy()
    if not candidates:
        raise ValueError("global_lane_lease_requires_candidate")
    refs = [item.objective_ref for item in candidates]
    if len(refs) != len(set(refs)):
        raise ValueError("global_lane_lease_objective_refs_must_be_unique")
    validated_leases = tuple(
        GlobalLaneLease.model_validate(item.model_dump(mode="json")) for item in active_leases
    )
    active_ids = [item.lease_id for item in validated_leases if item.blocks_at(now)]
    if len(active_ids) != len(set(active_ids)):
        raise ValueError("global_lane_lease_active_ids_must_be_unique")

    flattened = sorted(
        ((candidate, lane) for candidate in candidates for lane in candidate.plan.lanes),
        key=lambda pair: _lane_ranking(pair[0], pair[1]),
    )
    selected: list[GlobalLaneSelection] = []
    deferred: dict[str, tuple[str, ...]] = {}
    issued: list[GlobalLaneLease] = []
    stale_ids: list[str] = []

    for candidate, lane in flattened:
        key = _lane_key(candidate.objective_ref, lane.lane_id)
        if len(selected) >= rules.max_selected_lanes:
            deferred[key] = ("global_lane_capacity_deferred",)
            continue
        resources, idempotency_keys = _claim(lane)
        if not resources:
            selected.append(
                GlobalLaneSelection(
                    objective_ref=candidate.objective_ref,
                    tenant_id=candidate.tenant_id,
                    lane_id=lane.lane_id,
                    mutating=False,
                )
            )
            continue

        blockers, stale = _lease_conflicts(
            tenant_id=candidate.tenant_id,
            resources=resources,
            idempotency_keys=idempotency_keys,
            leases=(*validated_leases, *issued),
            now=now,
        )
        if blockers:
            deferred[key] = blockers
            stale_ids.extend(stale)
            continue

        lease = _build_lease(
            tenant_id=candidate.tenant_id,
            objective_ref=candidate.objective_ref,
            lane_id=lane.lane_id,
            resource_refs=resources,
            idempotency_keys=idempotency_keys,
            acquired_at=now,
            expires_at=now + timedelta(seconds=rules.lease_ttl_seconds),
        )
        issued.append(lease)
        selected.append(
            GlobalLaneSelection(
                objective_ref=candidate.objective_ref,
                tenant_id=candidate.tenant_id,
                lane_id=lane.lane_id,
                mutating=True,
                lease_id=lease.lease_id,
            )
        )

    return GlobalLaneLeaseAdmission(
        selected=tuple(selected),
        deferred=deferred,
        issued_leases=tuple(issued),
        blocking_stale_lease_ids=tuple(dict.fromkeys(stale_ids)),
    )


def admitted_plans_from_lane_leases(
    *,
    candidates: tuple[GlobalObjectiveCandidate, ...],
    admission: GlobalLaneLeaseAdmission,
) -> dict[str, ParallelMissionPlan]:
    """Project a lane-level admission back into executable per-objective plans."""

    selected_by_objective: dict[str, set[str]] = {}
    for item in admission.selected:
        selected_by_objective.setdefault(item.objective_ref, set()).add(item.lane_id)

    plans: dict[str, ParallelMissionPlan] = {}
    for candidate in candidates:
        selected_ids = selected_by_objective.get(candidate.objective_ref, set())
        if not selected_ids:
            continue
        lanes = tuple(lane for lane in candidate.plan.lanes if lane.lane_id in selected_ids)
        if len(lanes) != len(selected_ids):
            raise ValueError("global_lane_admission_references_unknown_lane")
        plans[candidate.objective_ref] = candidate.plan.model_copy(
            update={
                "lanes": lanes,
                "max_parallel_lanes": min(candidate.plan.max_parallel_lanes, len(lanes)),
            }
        )
    return plans
