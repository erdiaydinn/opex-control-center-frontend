"""Evidence-bound fan-out/fan-in composition for specialist Jarvis colonies.

The canonical swarm already executes independent lanes concurrently. This module
adds the convergence boundary: actual worker-produced artifacts may be published
to the shared blackboard, a reviewed Evidence colony verifies producer independence
and claim consistency, and only a verified bundle may become an executive synthesis
candidate.

This layer never executes tools, promotes Company World truth, proves causality or
creates a second confidence/verifier stack. Final answer quality remains owned by
the canonical grounded evidence/guard/critic pipeline.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, Field, model_validator

from .parallel_mission_orchestration import ParallelLaneDisposition
from .swarm_blackboard import (
    SwarmBlackboardEntry,
    SwarmBlackboardEntryKind,
    SwarmBlackboardLedger,
    append_blackboard_entry,
    build_blackboard_entry,
    visible_blackboard_entries,
)
from .swarm_colony_runtime import (
    SwarmColonyExecutionRound,
    SwarmColonyKind,
    SwarmColonyTopology,
)
from .swarm_worker_registry import SwarmWorkerRegistry

COLONY_FANOUT_FANIN_CONTRACT = "eay-colony-fanout-fanin-v1"


class ColonyEvidenceStance(str, Enum):
    SUPPORTS = "supports"
    REFUTES = "refutes"


class ColonyEvidenceStatus(str, Enum):
    VERIFIED = "verified"
    INSUFFICIENT = "insufficient"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


class ExecutiveSynthesisStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


class ColonyLaneArtifactPublication(BaseModel):
    contract: str = COLONY_FANOUT_FANIN_CONTRACT
    lane_id: str = Field(min_length=1)
    entry_id: str = Field(min_length=1)
    kind: SwarmBlackboardEntryKind
    subject_ref: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def publication_is_temporally_valid(self) -> "ColonyLaneArtifactPublication":
        _require_aware(self.observed_at, "colony_publication_observed_at_requires_timezone")
        _require_aware(self.recorded_at, "colony_publication_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("colony_publication_recorded_at_predates_observation")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("colony_publication_evidence_refs_must_be_unique")
        return self


class EvidenceColonyReview(BaseModel):
    contract: str = COLONY_FANOUT_FANIN_CONTRACT
    review_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    evidence_colony_ref: str = Field(min_length=1)
    reviewer_worker_id: str = Field(min_length=1)
    review_evidence_ref: str = Field(min_length=1)
    reviewed_at: datetime
    truth_authority_granted: bool = False
    decision_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def review_is_non_authoritative(self) -> "EvidenceColonyReview":
        _require_aware(self.reviewed_at, "evidence_colony_review_requires_timezone")
        if self.truth_authority_granted:
            raise ValueError("evidence_colony_review_never_grants_truth_authority")
        if self.decision_authority_granted:
            raise ValueError("evidence_colony_review_never_grants_decision_authority")
        if self.execution_authority_granted:
            raise ValueError("evidence_colony_review_never_grants_execution_authority")
        return self


class ColonyFanInPolicy(BaseModel):
    contract: str = COLONY_FANOUT_FANIN_CONTRACT
    tenant_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    evidence_colony_ref: str = Field(min_length=1)
    eligible_producer_colony_refs: tuple[str, ...] = Field(min_length=1)
    required_producer_colony_refs: tuple[str, ...] = ()
    minimum_independent_producer_colonies: int = Field(default=2, ge=1, le=32)
    allowed_entry_kinds: tuple[SwarmBlackboardEntryKind, ...] = (
        SwarmBlackboardEntryKind.OBSERVATION,
        SwarmBlackboardEntryKind.HYPOTHESIS,
        SwarmBlackboardEntryKind.FINDING,
        SwarmBlackboardEntryKind.SIMULATION,
        SwarmBlackboardEntryKind.BLOCKER,
    )
    policy_review_evidence_ref: str = Field(min_length=1)
    truth_authority_granted: bool = False
    causal_authority_granted: bool = False
    decision_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def policy_is_partitioned_and_non_authoritative(self) -> "ColonyFanInPolicy":
        eligible = set(self.eligible_producer_colony_refs)
        required = set(self.required_producer_colony_refs)
        if len(eligible) != len(self.eligible_producer_colony_refs):
            raise ValueError("colony_fanin_eligible_producers_must_be_unique")
        if len(required) != len(self.required_producer_colony_refs):
            raise ValueError("colony_fanin_required_producers_must_be_unique")
        if not required.issubset(eligible):
            raise ValueError("colony_fanin_required_producer_not_eligible")
        if self.evidence_colony_ref in eligible:
            raise ValueError("evidence_colony_cannot_be_producer_colony")
        if self.minimum_independent_producer_colonies > len(eligible):
            raise ValueError("colony_fanin_minimum_exceeds_eligible_producers")
        if not self.allowed_entry_kinds:
            raise ValueError("colony_fanin_requires_allowed_entry_kind")
        if len(self.allowed_entry_kinds) != len(set(self.allowed_entry_kinds)):
            raise ValueError("colony_fanin_allowed_entry_kinds_must_be_unique")
        if SwarmBlackboardEntryKind.ACTION_RESULT in self.allowed_entry_kinds:
            raise ValueError("colony_fanin_v1_forbids_action_result_as_claim_evidence")
        if self.truth_authority_granted:
            raise ValueError("colony_fanin_policy_never_grants_truth_authority")
        if self.causal_authority_granted:
            raise ValueError("colony_fanin_policy_never_grants_causal_authority")
        if self.decision_authority_granted:
            raise ValueError("colony_fanin_policy_never_grants_decision_authority")
        if self.execution_authority_granted:
            raise ValueError("colony_fanin_policy_never_grants_execution_authority")
        return self


class ColonyEvidenceClaimBinding(BaseModel):
    contract: str = COLONY_FANOUT_FANIN_CONTRACT
    entry_id: str = Field(min_length=1)
    entry_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposition_ref: str = Field(min_length=1)
    stance: ColonyEvidenceStance


class ColonyEvidenceBundle(BaseModel):
    contract: str = COLONY_FANOUT_FANIN_CONTRACT
    tenant_id: str
    objective_ref: str
    status: ColonyEvidenceStatus
    evidence_colony_ref: str
    reviewer_worker_id: str
    review_evidence_ref: str
    policy_review_evidence_ref: str
    as_of: datetime
    producer_colony_refs: tuple[str, ...]
    support_entry_refs: tuple[str, ...]
    support_entry_fingerprints: tuple[str, ...]
    proposition_refs: tuple[str, ...]
    grounded_evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    truth_authority_granted: bool = False
    causal_claim_proven: bool = False
    decision_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def bundle_is_integral_and_non_authoritative(self) -> "ColonyEvidenceBundle":
        _require_aware(self.as_of, "colony_evidence_bundle_as_of_requires_timezone")
        if self.truth_authority_granted:
            raise ValueError("colony_evidence_bundle_never_grants_truth_authority")
        if self.causal_claim_proven:
            raise ValueError("colony_evidence_bundle_never_proves_causality")
        if self.decision_authority_granted:
            raise ValueError("colony_evidence_bundle_never_grants_decision_authority")
        if self.execution_authority_granted:
            raise ValueError("colony_evidence_bundle_never_grants_execution_authority")
        for values, error in (
            (self.producer_colony_refs, "colony_evidence_bundle_producers_must_be_unique"),
            (self.support_entry_refs, "colony_evidence_bundle_entries_must_be_unique"),
            (
                self.support_entry_fingerprints,
                "colony_evidence_bundle_entry_fingerprints_must_be_unique",
            ),
            (self.proposition_refs, "colony_evidence_bundle_propositions_must_be_unique"),
            (
                self.grounded_evidence_refs,
                "colony_evidence_bundle_evidence_refs_must_be_unique",
            ),
            (self.artifact_refs, "colony_evidence_bundle_artifacts_must_be_unique"),
            (self.blockers, "colony_evidence_bundle_blockers_must_be_unique"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(error)
        expected = _fingerprint(_model_payload(self))
        if self.fingerprint != expected:
            raise ValueError("colony_evidence_bundle_fingerprint_mismatch")
        return self


class ExecutiveSynthesisCandidate(BaseModel):
    contract: str = COLONY_FANOUT_FANIN_CONTRACT
    tenant_id: str
    objective_ref: str
    status: ExecutiveSynthesisStatus
    evidence_bundle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_colony_ref: str
    producer_colony_refs: tuple[str, ...]
    grounded_evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    canonical_grounded_guard_required: bool = True
    private_chain_of_thought_exposed: bool = False
    truth_authority_granted: bool = False
    decision_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def synthesis_is_integral_and_non_authoritative(self) -> "ExecutiveSynthesisCandidate":
        if not self.canonical_grounded_guard_required:
            raise ValueError("executive_synthesis_requires_canonical_grounded_guard")
        if self.private_chain_of_thought_exposed:
            raise ValueError("executive_synthesis_private_chain_of_thought_forbidden")
        if self.truth_authority_granted:
            raise ValueError("executive_synthesis_never_grants_truth_authority")
        if self.decision_authority_granted:
            raise ValueError("executive_synthesis_never_grants_decision_authority")
        if self.execution_authority_granted:
            raise ValueError("executive_synthesis_never_grants_execution_authority")
        expected = _fingerprint(_model_payload(self))
        if self.fingerprint != expected:
            raise ValueError("executive_synthesis_fingerprint_mismatch")
        return self


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _normalize_payload(value: Any) -> Any:
    """Canonicalize builder and validated-model payloads identically.

    Pydantic's JSON mode serializes UTC datetimes with ``Z`` while a hand-built
    ``datetime.isoformat()`` value uses ``+00:00``. Hashing those two representations
    directly creates false integrity failures. We normalize from Python values on both
    sides so enums, tuples and timezone-aware datetimes have one deterministic form.
    """

    if isinstance(value, BaseModel):
        return _normalize_payload(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _normalize_payload(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize_payload(item) for item in value]
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _normalize_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _model_payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="python")
    payload.pop("fingerprint", None)
    return _normalize_payload(payload)


def _worker_colony_ref(
    *,
    worker_id: str,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
) -> str:
    workers = [item for item in registry.workers if item.worker_id == worker_id]
    if len(workers) != 1:
        raise ValueError("colony_fanin_worker_not_registered")
    worker = workers[0]
    if registry.tenant_id != topology.tenant_id or worker.tenant_id != topology.tenant_id:
        raise ValueError("colony_fanin_worker_topology_tenant_mismatch")
    matches = [
        colony.colony_ref
        for colony in topology.colonies
        if worker.worker_class in colony.worker_classes
    ]
    if len(matches) != 1:
        raise ValueError("colony_fanin_worker_colony_unresolved")
    return matches[0]


def _validate_review_identity(
    *,
    review: EvidenceColonyReview,
    policy: ColonyFanInPolicy,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
) -> None:
    if review.tenant_id != policy.tenant_id or topology.tenant_id != policy.tenant_id:
        raise ValueError("colony_fanin_review_tenant_mismatch")
    if review.objective_ref != policy.objective_ref:
        raise ValueError("colony_fanin_review_objective_mismatch")
    if review.evidence_colony_ref != policy.evidence_colony_ref:
        raise ValueError("colony_fanin_review_colony_mismatch")
    colonies = [
        item for item in topology.colonies if item.colony_ref == policy.evidence_colony_ref
    ]
    if len(colonies) != 1 or colonies[0].kind is not SwarmColonyKind.EVIDENCE:
        raise ValueError("colony_fanin_review_requires_evidence_colony")
    worker_colony = _worker_colony_ref(
        worker_id=review.reviewer_worker_id,
        registry=registry,
        topology=topology,
    )
    if worker_colony != policy.evidence_colony_ref:
        raise ValueError("colony_fanin_reviewer_not_in_evidence_colony")


def publish_colony_round_artifacts(
    *,
    ledger: SwarmBlackboardLedger,
    colony_round: SwarmColonyExecutionRound,
    publications: tuple[ColonyLaneArtifactPublication, ...],
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
) -> SwarmBlackboardLedger:
    """Publish only artifacts from lanes selected by the canonical executed wave."""

    if ledger.tenant_id != colony_round.execution.wave.tenant_id:
        raise ValueError("colony_publication_ledger_tenant_mismatch")
    if ledger.objective_ref != colony_round.execution.wave.objective_ref:
        raise ValueError("colony_publication_ledger_objective_mismatch")
    if registry.tenant_id != ledger.tenant_id or topology.tenant_id != ledger.tenant_id:
        raise ValueError("colony_publication_runtime_tenant_mismatch")

    publication_map = {item.lane_id: item for item in publications}
    if len(publication_map) != len(publications):
        raise ValueError("colony_publication_lane_ids_must_be_unique")

    assignment_map = {
        item.lane_id: item for item in colony_round.colony_wave.assignments
    }
    result_map = {item.lane_id: item for item in colony_round.execution.results}
    unknown = set(publication_map) - set(assignment_map)
    if unknown:
        raise ValueError("colony_publication_unselected_lane_forbidden")

    updated = ledger
    for lane_id, publication in publication_map.items():
        assignment = assignment_map[lane_id]
        result = result_map.get(lane_id)
        if result is None:
            raise ValueError("colony_publication_selected_lane_result_missing")
        if result.disposition not in {
            ParallelLaneDisposition.EXECUTED,
            ParallelLaneDisposition.FAILED,
        }:
            raise ValueError("colony_publication_nonexecuted_lane_forbidden")
        if (
            result.disposition is ParallelLaneDisposition.FAILED
            and publication.kind is not SwarmBlackboardEntryKind.BLOCKER
        ):
            raise ValueError("colony_publication_failed_lane_requires_blocker")
        entry = build_blackboard_entry(
            entry_id=publication.entry_id,
            tenant_id=ledger.tenant_id,
            objective_ref=ledger.objective_ref,
            colony_ref=assignment.colony_ref,
            worker_id=assignment.worker_id,
            kind=publication.kind,
            subject_ref=publication.subject_ref,
            artifact_ref=publication.artifact_ref,
            evidence_refs=publication.evidence_refs,
            observed_at=publication.observed_at,
            recorded_at=publication.recorded_at,
            confidence=publication.confidence,
        )
        updated = append_blackboard_entry(
            ledger=updated,
            entry=entry,
            registry=registry,
            topology=topology,
        )
    return updated


def _rehydrate_visible_entries(
    *,
    ledger: SwarmBlackboardLedger,
    as_of: datetime,
) -> tuple[SwarmBlackboardEntry, ...]:
    entries = visible_blackboard_entries(ledger=ledger, as_of=as_of)
    return tuple(
        SwarmBlackboardEntry.model_validate(item.model_dump(mode="json"))
        for item in entries
    )


def verify_colony_evidence(
    *,
    ledger: SwarmBlackboardLedger,
    policy: ColonyFanInPolicy,
    review: EvidenceColonyReview,
    claims: tuple[ColonyEvidenceClaimBinding, ...],
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
    as_of: datetime,
) -> ColonyEvidenceBundle:
    """Verify integrity, producer independence and contradictions fail-closed."""

    _require_aware(as_of, "colony_fanin_as_of_requires_timezone")
    if ledger.tenant_id != policy.tenant_id or ledger.objective_ref != policy.objective_ref:
        raise ValueError("colony_fanin_ledger_policy_binding_mismatch")
    if review.reviewed_at < as_of:
        raise ValueError("colony_fanin_review_predates_as_of")
    _validate_review_identity(
        review=review,
        policy=policy,
        registry=registry,
        topology=topology,
    )

    if len(
        {(item.entry_id, item.proposition_ref, item.stance) for item in claims}
    ) != len(claims):
        raise ValueError("colony_fanin_claim_bindings_must_be_unique")

    visible = _rehydrate_visible_entries(ledger=ledger, as_of=as_of)
    visible_map = {item.entry_id: item for item in visible}
    eligible = set(policy.eligible_producer_colony_refs)
    allowed_kinds = set(policy.allowed_entry_kinds)

    selected_entries: dict[str, SwarmBlackboardEntry] = {}
    proposition_stances: dict[
        str, dict[ColonyEvidenceStance, set[str]]
    ] = {}
    blockers: list[str] = []

    for claim in claims:
        entry = visible_map.get(claim.entry_id)
        if entry is None:
            blockers.append("colony_fanin_claim_entry_not_visible")
            continue
        if entry.fingerprint != claim.entry_fingerprint:
            raise ValueError("colony_fanin_claim_entry_fingerprint_mismatch")
        if entry.colony_ref not in eligible:
            blockers.append("colony_fanin_claim_producer_not_eligible")
            continue
        if entry.kind is SwarmBlackboardEntryKind.ACTION_RESULT:
            blockers.append("colony_fanin_action_result_requires_verified_action_bridge")
            continue
        if entry.kind not in allowed_kinds:
            blockers.append("colony_fanin_claim_entry_kind_not_allowed")
            continue

        actual_colony = _worker_colony_ref(
            worker_id=entry.worker_id,
            registry=registry,
            topology=topology,
        )
        if actual_colony != entry.colony_ref:
            raise ValueError("colony_fanin_blackboard_producer_colony_mismatch")
        selected_entries[entry.entry_id] = entry
        by_stance = proposition_stances.setdefault(
            claim.proposition_ref,
            {
                ColonyEvidenceStance.SUPPORTS: set(),
                ColonyEvidenceStance.REFUTES: set(),
            },
        )
        by_stance[claim.stance].add(entry.colony_ref)

    producer_colonies = tuple(
        sorted({item.colony_ref for item in selected_entries.values()})
    )
    missing_required = sorted(
        set(policy.required_producer_colony_refs) - set(producer_colonies)
    )
    if missing_required:
        blockers.append("colony_fanin_required_producer_missing")
    if len(producer_colonies) < policy.minimum_independent_producer_colonies:
        blockers.append("colony_fanin_independent_producer_quorum_missing")

    blocking_entries = [
        item
        for item in selected_entries.values()
        if item.kind is SwarmBlackboardEntryKind.BLOCKER
    ]
    if blocking_entries:
        blockers.append("colony_fanin_producer_blocker_present")

    conflict_refs = [
        proposition_ref
        for proposition_ref, stances in proposition_stances.items()
        if stances[ColonyEvidenceStance.SUPPORTS]
        and stances[ColonyEvidenceStance.REFUTES]
    ]
    if conflict_refs:
        blockers.append("colony_fanin_independent_claim_conflict")

    blockers = list(dict.fromkeys(blockers))
    if conflict_refs:
        status = ColonyEvidenceStatus.CONFLICT
    elif blocking_entries:
        status = ColonyEvidenceStatus.BLOCKED
    elif blockers:
        status = ColonyEvidenceStatus.INSUFFICIENT
    else:
        status = ColonyEvidenceStatus.VERIFIED

    entries = tuple(sorted(selected_entries.values(), key=lambda item: item.entry_id))
    evidence_refs = tuple(
        dict.fromkeys(ref for item in entries for ref in item.evidence_refs)
    )
    artifact_refs = tuple(dict.fromkeys(item.artifact_ref for item in entries))
    proposition_refs = tuple(sorted(proposition_stances))

    draft: dict[str, Any] = {
        "contract": COLONY_FANOUT_FANIN_CONTRACT,
        "tenant_id": policy.tenant_id,
        "objective_ref": policy.objective_ref,
        "status": status.value,
        "evidence_colony_ref": policy.evidence_colony_ref,
        "reviewer_worker_id": review.reviewer_worker_id,
        "review_evidence_ref": review.review_evidence_ref,
        "policy_review_evidence_ref": policy.policy_review_evidence_ref,
        "as_of": as_of.isoformat(),
        "producer_colony_refs": list(producer_colonies),
        "support_entry_refs": [item.entry_id for item in entries],
        "support_entry_fingerprints": [item.fingerprint for item in entries],
        "proposition_refs": list(proposition_refs),
        "grounded_evidence_refs": list(evidence_refs),
        "artifact_refs": list(artifact_refs),
        "blockers": blockers,
        "truth_authority_granted": False,
        "causal_claim_proven": False,
        "decision_authority_granted": False,
        "execution_authority_granted": False,
    }
    return ColonyEvidenceBundle.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def build_executive_synthesis_candidate(
    bundle: ColonyEvidenceBundle,
) -> ExecutiveSynthesisCandidate:
    """Create only an observable support envelope for canonical grounded synthesis."""

    bundle = ColonyEvidenceBundle.model_validate(bundle.model_dump(mode="json"))
    ready = bundle.status is ColonyEvidenceStatus.VERIFIED
    blockers = () if ready else (
        *bundle.blockers,
        "executive_synthesis_requires_verified_colony_evidence",
    )
    draft: dict[str, Any] = {
        "contract": COLONY_FANOUT_FANIN_CONTRACT,
        "tenant_id": bundle.tenant_id,
        "objective_ref": bundle.objective_ref,
        "status": (
            ExecutiveSynthesisStatus.READY.value
            if ready
            else ExecutiveSynthesisStatus.BLOCKED.value
        ),
        "evidence_bundle_fingerprint": bundle.fingerprint,
        "evidence_colony_ref": bundle.evidence_colony_ref,
        "producer_colony_refs": list(bundle.producer_colony_refs),
        "grounded_evidence_refs": list(bundle.grounded_evidence_refs),
        "artifact_refs": list(bundle.artifact_refs),
        "blockers": list(dict.fromkeys(blockers)),
        "canonical_grounded_guard_required": True,
        "private_chain_of_thought_exposed": False,
        "truth_authority_granted": False,
        "decision_authority_granted": False,
        "execution_authority_granted": False,
    }
    return ExecutiveSynthesisCandidate.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )
