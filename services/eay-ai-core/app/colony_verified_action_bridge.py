"""Bridge Action Colony blackboard results to canonical verified mission-action proof.

An Action Colony worker declaring ``ACTION_RESULT`` is not evidence that a side effect
actually happened. This bridge accepts only the existing integrity-sealed
``VerifiedMissionActionProof`` produced from durable mission state, execution outcome,
authoritative effect verification and transaction/evidence agreement.

The binding is reference-only, tenant/objective bound and historical-cutoff aware. It
proves only that the referenced action reached the canonical VERIFIED_ACTION boundary;
it never proves business correctness, causality, decision quality or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .real_world_timeline_learning import VerifiedMissionActionProof
from .swarm_blackboard import SwarmBlackboardEntry, SwarmBlackboardEntryKind
from .swarm_colony_runtime import SwarmColonyKind, SwarmColonyTopology
from .swarm_worker_registry import SwarmWorkerRegistry

COLONY_VERIFIED_ACTION_BRIDGE_CONTRACT = "eay-colony-verified-action-bridge-v1"


class ColonyVerifiedActionBinding(BaseModel):
    contract: str = COLONY_VERIFIED_ACTION_BRIDGE_CONTRACT
    tenant_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    producer_colony_ref: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    entry_id: str = Field(min_length=1)
    entry_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    transaction_ref: str = Field(min_length=1)
    verified_action_proof_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_action_proof_ref: str = Field(min_length=1)
    proof_checkpoint_sequence: int = Field(ge=1)
    executed_at: datetime
    proof_checkpointed_at: datetime
    entry_recorded_at: datetime
    bound_at: datetime
    grounded_evidence_refs: tuple[str, ...] = Field(min_length=1)
    truth_authority_granted: bool = False
    causal_claim_proven: bool = False
    decision_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def binding_is_integral_and_non_authoritative(self) -> "ColonyVerifiedActionBinding":
        for value, error in (
            (self.executed_at, "colony_verified_action_executed_at_requires_timezone"),
            (
                self.proof_checkpointed_at,
                "colony_verified_action_checkpointed_at_requires_timezone",
            ),
            (
                self.entry_recorded_at,
                "colony_verified_action_entry_recorded_at_requires_timezone",
            ),
            (self.bound_at, "colony_verified_action_bound_at_requires_timezone"),
        ):
            _require_aware(value, error)
        if self.proof_checkpointed_at < self.executed_at:
            raise ValueError("colony_verified_action_checkpoint_precedes_execution")
        if self.entry_recorded_at < self.proof_checkpointed_at:
            raise ValueError("colony_verified_action_entry_predates_proof")
        if self.bound_at < self.entry_recorded_at:
            raise ValueError("colony_verified_action_binding_predates_entry")
        if self.truth_authority_granted:
            raise ValueError("colony_verified_action_never_grants_truth_authority")
        if self.causal_claim_proven:
            raise ValueError("colony_verified_action_never_proves_causality")
        if self.decision_authority_granted:
            raise ValueError("colony_verified_action_never_grants_decision_authority")
        if self.execution_authority_granted:
            raise ValueError("colony_verified_action_never_grants_execution_authority")
        if len(self.grounded_evidence_refs) != len(set(self.grounded_evidence_refs)):
            raise ValueError("colony_verified_action_evidence_refs_must_be_unique")
        expected = _fingerprint(_binding_payload(self))
        if self.fingerprint != expected:
            raise ValueError("colony_verified_action_binding_fingerprint_mismatch")
        return self


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _canonical_hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _binding_payload(binding: ColonyVerifiedActionBinding) -> dict[str, Any]:
    return {
        "contract": binding.contract,
        "tenant_id": binding.tenant_id,
        "objective_ref": binding.objective_ref,
        "producer_colony_ref": binding.producer_colony_ref,
        "worker_id": binding.worker_id,
        "entry_id": binding.entry_id,
        "entry_fingerprint": binding.entry_fingerprint,
        "action_id": binding.action_id,
        "mission_id": binding.mission_id,
        "capability_ref": binding.capability_ref,
        "transaction_ref": binding.transaction_ref,
        "verified_action_proof_fingerprint": binding.verified_action_proof_fingerprint,
        "verified_action_proof_ref": binding.verified_action_proof_ref,
        "proof_checkpoint_sequence": binding.proof_checkpoint_sequence,
        "executed_at": binding.executed_at.isoformat(),
        "proof_checkpointed_at": binding.proof_checkpointed_at.isoformat(),
        "entry_recorded_at": binding.entry_recorded_at.isoformat(),
        "bound_at": binding.bound_at.isoformat(),
        "grounded_evidence_refs": sorted(binding.grounded_evidence_refs),
        "truth_authority_granted": False,
        "causal_claim_proven": False,
        "decision_authority_granted": False,
        "execution_authority_granted": False,
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    return _canonical_hash(payload)


def validate_colony_verified_action_binding(
    binding: ColonyVerifiedActionBinding,
) -> ColonyVerifiedActionBinding:
    """Rehydrate to close Pydantic ``model_copy`` validation bypass."""

    return ColonyVerifiedActionBinding.model_validate(binding.model_dump(mode="json"))


def _worker_action_colony_ref(
    *,
    worker_id: str,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
) -> str:
    if registry.tenant_id != topology.tenant_id:
        raise ValueError("colony_verified_action_registry_topology_tenant_mismatch")
    workers = [item for item in registry.workers if item.worker_id == worker_id]
    if len(workers) != 1:
        raise ValueError("colony_verified_action_worker_not_registered")
    worker = workers[0]
    if worker.tenant_id != topology.tenant_id:
        raise ValueError("colony_verified_action_worker_tenant_mismatch")
    matches = [
        colony
        for colony in topology.colonies
        if worker.worker_class in colony.worker_classes
    ]
    if len(matches) != 1:
        raise ValueError("colony_verified_action_worker_colony_unresolved")
    colony = matches[0]
    if colony.kind is not SwarmColonyKind.ACTION or not colony.may_handle_side_effect_lanes:
        raise ValueError("colony_verified_action_requires_action_colony")
    return colony.colony_ref


def bind_verified_action_result(
    *,
    entry: SwarmBlackboardEntry,
    proof: VerifiedMissionActionProof,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
    bound_at: datetime,
) -> ColonyVerifiedActionBinding:
    """Bind one blackboard ActionResult to the existing strong mission-action proof."""

    _require_aware(bound_at, "colony_verified_action_bound_at_requires_timezone")
    entry = SwarmBlackboardEntry.model_validate(entry.model_dump(mode="json"))
    proof = VerifiedMissionActionProof.model_validate(proof.model_dump(mode="json"))

    if entry.kind is not SwarmBlackboardEntryKind.ACTION_RESULT:
        raise ValueError("colony_verified_action_requires_action_result_entry")
    if entry.tenant_id != proof.tenant_id:
        raise ValueError("colony_verified_action_proof_tenant_mismatch")

    action_colony_ref = _worker_action_colony_ref(
        worker_id=entry.worker_id,
        registry=registry,
        topology=topology,
    )
    if entry.colony_ref != action_colony_ref:
        raise ValueError("colony_verified_action_entry_colony_mismatch")

    expected_subject_ref = f"action://{proof.action_id}"
    proof_ref = f"verified-action-proof://{proof.fingerprint}"
    if entry.subject_ref != expected_subject_ref:
        raise ValueError("colony_verified_action_subject_ref_mismatch")
    if entry.artifact_ref != proof_ref:
        raise ValueError("colony_verified_action_proof_ref_mismatch")
    if entry.observed_at < proof.executed_at:
        raise ValueError("colony_verified_action_observation_predates_execution")
    if entry.recorded_at < proof.checkpointed_at:
        raise ValueError("colony_verified_action_entry_predates_proof")
    if bound_at < entry.recorded_at:
        raise ValueError("colony_verified_action_binding_predates_entry")

    grounded_evidence_refs = tuple(
        dict.fromkeys(
            (
                *proof.verification_evidence_refs,
                *proof.execution_evidence_refs,
                *proof.receipt_evidence_refs,
                proof.transaction_ref,
                proof_ref,
            )
        )
    )
    payload = dict(
        tenant_id=entry.tenant_id,
        objective_ref=entry.objective_ref,
        producer_colony_ref=entry.colony_ref,
        worker_id=entry.worker_id,
        entry_id=entry.entry_id,
        entry_fingerprint=entry.fingerprint,
        action_id=proof.action_id,
        mission_id=proof.mission_id,
        capability_ref=proof.capability_ref,
        transaction_ref=proof.transaction_ref,
        verified_action_proof_fingerprint=proof.fingerprint,
        verified_action_proof_ref=proof_ref,
        proof_checkpoint_sequence=proof.checkpoint_sequence,
        executed_at=proof.executed_at,
        proof_checkpointed_at=proof.checkpointed_at,
        entry_recorded_at=entry.recorded_at,
        bound_at=bound_at,
        grounded_evidence_refs=grounded_evidence_refs,
    )
    provisional = ColonyVerifiedActionBinding.model_construct(
        contract=COLONY_VERIFIED_ACTION_BRIDGE_CONTRACT,
        **payload,
        truth_authority_granted=False,
        causal_claim_proven=False,
        decision_authority_granted=False,
        execution_authority_granted=False,
        fingerprint="0" * 64,
    )
    return ColonyVerifiedActionBinding(
        **payload,
        fingerprint=_fingerprint(_binding_payload(provisional)),
    )
