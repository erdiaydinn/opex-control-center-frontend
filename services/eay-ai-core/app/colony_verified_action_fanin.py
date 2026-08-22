"""Compose canonical VERIFIED_ACTION proof into the existing colony fan-in verifier.

The base fan-in deliberately rejects raw ``ACTION_RESULT`` entries. This module keeps
that fail-closed default and provides the only reviewed upgrade path: an ActionResult
must carry an exact ``ColonyVerifiedActionBinding`` derived from the existing strong
``VerifiedMissionActionProof``. The binding is converted into an ephemeral reference-
only evidence proxy and then delegated to the canonical ``verify_colony_evidence``
function. No second quorum/conflict verifier is introduced.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from .colony_fanout_fanin_runtime import (
    ColonyEvidenceBundle,
    ColonyEvidenceClaimBinding,
    ColonyEvidenceStance,
    ColonyFanInPolicy,
    EvidenceColonyReview,
    verify_colony_evidence,
)
from .colony_verified_action_bridge import (
    ColonyVerifiedActionBinding,
    validate_colony_verified_action_binding,
)
from .swarm_blackboard import (
    SwarmBlackboardEntry,
    SwarmBlackboardEntryKind,
    SwarmBlackboardLedger,
    append_blackboard_entry,
    build_blackboard_entry,
    visible_blackboard_entries,
)
from .swarm_colony_runtime import SwarmColonyTopology
from .swarm_worker_registry import SwarmWorkerRegistry

COLONY_VERIFIED_ACTION_FANIN_CONTRACT = "eay-colony-verified-action-fanin-v1"


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _validated_binding_map(
    bindings: Mapping[str, ColonyVerifiedActionBinding] | None,
) -> dict[str, ColonyVerifiedActionBinding]:
    validated: dict[str, ColonyVerifiedActionBinding] = {}
    for key, candidate in dict(bindings or {}).items():
        binding = validate_colony_verified_action_binding(candidate)
        if key != binding.entry_id:
            raise ValueError("colony_verified_action_binding_key_mismatch")
        if key in validated:
            raise ValueError("colony_verified_action_binding_entry_duplicate")
        validated[key] = binding
    return validated


def _action_proxy_entry(
    *,
    entry: SwarmBlackboardEntry,
    binding: ColonyVerifiedActionBinding,
) -> SwarmBlackboardEntry:
    return build_blackboard_entry(
        entry_id=(
            "verified-action-bridge:"
            + entry.entry_id
            + ":"
            + binding.fingerprint[:16]
        ),
        tenant_id=entry.tenant_id,
        objective_ref=entry.objective_ref,
        colony_ref=entry.colony_ref,
        worker_id=entry.worker_id,
        kind=SwarmBlackboardEntryKind.FINDING,
        subject_ref=f"action://{binding.action_id}",
        artifact_ref=binding.verified_action_proof_ref,
        evidence_refs=binding.grounded_evidence_refs,
        observed_at=max(entry.observed_at, binding.proof_checkpointed_at),
        recorded_at=binding.bound_at,
        confidence=1.0,
    )


def verify_colony_evidence_with_verified_actions(
    *,
    ledger: SwarmBlackboardLedger,
    policy: ColonyFanInPolicy,
    review: EvidenceColonyReview,
    claims: tuple[ColonyEvidenceClaimBinding, ...],
    verified_action_bindings: Mapping[str, ColonyVerifiedActionBinding] | None,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
    as_of: datetime,
) -> ColonyEvidenceBundle:
    """Upgrade only strongly verified ActionResults, then delegate to base fan-in."""

    _require_aware(as_of, "colony_verified_action_fanin_as_of_requires_timezone")
    bindings = _validated_binding_map(verified_action_bindings)
    visible = visible_blackboard_entries(ledger=ledger, as_of=as_of)
    visible_map = {
        item.entry_id: SwarmBlackboardEntry.model_validate(item.model_dump(mode="json"))
        for item in visible
    }

    temporary_ledger = ledger
    translated_claims: list[ColonyEvidenceClaimBinding] = []
    referenced_action_bindings: set[str] = set()

    for claim in claims:
        entry = visible_map.get(claim.entry_id)
        if entry is None or entry.kind is not SwarmBlackboardEntryKind.ACTION_RESULT:
            translated_claims.append(claim)
            continue

        binding = bindings.get(entry.entry_id)
        if binding is None:
            # Preserve the base verifier's explicit fail-closed blocker for raw action results.
            translated_claims.append(claim)
            continue
        referenced_action_bindings.add(entry.entry_id)

        if binding.tenant_id != entry.tenant_id or binding.tenant_id != policy.tenant_id:
            raise ValueError("colony_verified_action_fanin_tenant_mismatch")
        if binding.objective_ref != entry.objective_ref or binding.objective_ref != policy.objective_ref:
            raise ValueError("colony_verified_action_fanin_objective_mismatch")
        if binding.entry_id != entry.entry_id or binding.entry_fingerprint != entry.fingerprint:
            raise ValueError("colony_verified_action_fanin_entry_binding_mismatch")
        if binding.producer_colony_ref != entry.colony_ref or binding.worker_id != entry.worker_id:
            raise ValueError("colony_verified_action_fanin_producer_binding_mismatch")
        if binding.bound_at > as_of:
            # The proof existed later than this historical replay point; do not smuggle it backward.
            translated_claims.append(claim)
            continue

        expected_proposition = f"action-applied://{binding.action_id}"
        if claim.proposition_ref != expected_proposition:
            raise ValueError("colony_verified_action_fanin_proposition_scope_mismatch")
        if claim.stance is not ColonyEvidenceStance.SUPPORTS:
            raise ValueError("colony_verified_action_fanin_verified_action_must_support")

        proxy = _action_proxy_entry(entry=entry, binding=binding)
        temporary_ledger = append_blackboard_entry(
            ledger=temporary_ledger,
            entry=proxy,
            registry=registry,
            topology=topology,
        )
        translated_claims.append(
            ColonyEvidenceClaimBinding(
                entry_id=proxy.entry_id,
                entry_fingerprint=proxy.fingerprint,
                proposition_ref=claim.proposition_ref,
                stance=claim.stance,
            )
        )

    unused = set(bindings) - referenced_action_bindings
    if unused:
        raise ValueError("colony_verified_action_fanin_unreferenced_binding_forbidden")

    return verify_colony_evidence(
        ledger=temporary_ledger,
        policy=policy,
        review=review,
        claims=tuple(translated_claims),
        registry=registry,
        topology=topology,
        as_of=as_of,
    )
