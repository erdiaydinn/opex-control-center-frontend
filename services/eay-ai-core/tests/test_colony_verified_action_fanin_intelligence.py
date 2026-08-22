from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.colony_fanout_fanin_runtime import (
    ColonyEvidenceClaimBinding,
    ColonyEvidenceStance,
    ColonyEvidenceStatus,
    ColonyFanInPolicy,
    EvidenceColonyReview,
    ExecutiveSynthesisStatus,
    build_executive_synthesis_candidate,
    verify_colony_evidence,
)
from app.colony_verified_action_bridge import bind_verified_action_result
from app.colony_verified_action_fanin import verify_colony_evidence_with_verified_actions
from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint, record_step_result
from app.outcome_learning import GovernedActionReceipt
from app.playwright_mission_adapter import BrowserEffectVerification, EffectVerificationStatus
from app.real_world_timeline_learning import build_verified_mission_action_proof
from app.swarm_blackboard import (
    SwarmBlackboardEntryKind,
    SwarmBlackboardLedger,
    append_blackboard_entry,
    build_blackboard_entry,
)
from app.swarm_colony_runtime import (
    SwarmColonyDescriptor,
    SwarmColonyKind,
    SwarmColonyTopology,
)
from app.swarm_worker_registry import (
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
)
from app.parallel_mission_scheduler import LaneSchedulingClass

NOW = datetime(2026, 8, 19, 12, 30, tzinfo=timezone.utc)
TENANT = "YS_TR"
OBJECTIVE = "objective://verified-action-fanin"
ACTION_ID = "action-stock-adjustment"


def _worker(worker_id, worker_class, scheduling_class):
    return SwarmWorkerDescriptor(
        worker_id=worker_id,
        tenant_id=TENANT,
        worker_class=worker_class,
        supported_scheduling_classes=(scheduling_class,),
    )


def _registry():
    return SwarmWorkerRegistry(
        tenant_id=TENANT,
        workers=(
            _worker("worker-data", SwarmWorkerClass.COMPANY_READ, LaneSchedulingClass.COMPANY_READ),
            _worker("worker-action", SwarmWorkerClass.EXECUTION, LaneSchedulingClass.EXECUTION),
            _worker("worker-evidence", SwarmWorkerClass.REASONING, LaneSchedulingClass.INTERACTIVE),
        ),
    )


def _topology():
    return SwarmColonyTopology(
        tenant_id=TENANT,
        colonies=(
            SwarmColonyDescriptor(
                colony_ref="colony://data",
                tenant_id=TENANT,
                kind=SwarmColonyKind.DATA,
                worker_classes=(SwarmWorkerClass.COMPANY_READ,),
            ),
            SwarmColonyDescriptor(
                colony_ref="colony://action",
                tenant_id=TENANT,
                kind=SwarmColonyKind.ACTION,
                worker_classes=(SwarmWorkerClass.EXECUTION,),
                may_handle_side_effect_lanes=True,
            ),
            SwarmColonyDescriptor(
                colony_ref="colony://evidence",
                tenant_id=TENANT,
                kind=SwarmColonyKind.EVIDENCE,
                worker_classes=(SwarmWorkerClass.REASONING,),
            ),
        ),
    )


def _review():
    return EvidenceColonyReview(
        review_id="review-action-fanin",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        evidence_colony_ref="colony://evidence",
        reviewer_worker_id="worker-evidence",
        review_evidence_ref="evidence-review://verified-action-fanin",
        reviewed_at=NOW + timedelta(minutes=5),
    )


def _policy():
    return ColonyFanInPolicy(
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        evidence_colony_ref="colony://evidence",
        eligible_producer_colony_refs=("colony://action", "colony://data"),
        required_producer_colony_refs=("colony://action", "colony://data"),
        minimum_independent_producer_colonies=2,
        policy_review_evidence_ref="review://policy/verified-action-fanin",
    )


def _proof():
    step = MissionStep(
        step_id="adjust-stock",
        description="Apply authorized stock adjustment",
        side_effect=True,
        idempotency_key="opaque-action-idempotency",
        effect_verifier_ref="capability://inventory.readback",
    )
    definition = MissionDefinition(
        mission_id="mission-stock-adjustment",
        objective="Apply verified inventory action",
        tenant_id=TENANT,
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="adjust-stock",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref="capability://inventory.adjust",
    )
    transaction_ref = "transaction://inventory/verified-123"
    verification = BrowserEffectVerification(
        status=EffectVerificationStatus.VERIFIED_APPLIED,
        evidence_refs=("evidence://authoritative-readback",),
        transaction_ref=transaction_ref,
    )
    execution = CapabilityExecutionOutcome(
        succeeded=True,
        effect_verified=True,
        ambiguous_outcome=False,
        evidence_refs=("evidence://execution", "evidence://authoritative-readback"),
        transaction_ref=transaction_ref,
    )
    checkpoint = record_step_result(
        definition,
        new_checkpoint(definition, now=NOW - timedelta(seconds=5)),
        step_id="adjust-stock",
        succeeded=True,
        evidence_refs=(
            "evidence://execution",
            "evidence://authoritative-readback",
            "evidence://governed-action-receipt",
            transaction_ref,
        ),
        now=NOW + timedelta(seconds=10),
    )
    receipt = GovernedActionReceipt(
        action_id=ACTION_ID,
        decision_id="decision-stock-adjustment",
        tenant_id=TENANT,
        executed_at=NOW + timedelta(seconds=3),
        capability_ref="capability://inventory.adjust",
        effect_verified=True,
        evidence_refs=("evidence://governed-action-receipt",),
    )
    return build_verified_mission_action_proof(
        receipt=receipt,
        definition=definition,
        checkpoint=checkpoint,
        spec=spec,
        execution_outcome=execution,
        verification=verification,
    )


def _ledger_with_action_and_data(proof):
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    action = build_blackboard_entry(
        entry_id="action-result-1",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref="colony://action",
        worker_id="worker-action",
        kind=SwarmBlackboardEntryKind.ACTION_RESULT,
        subject_ref=f"action://{proof.action_id}",
        artifact_ref=f"verified-action-proof://{proof.fingerprint}",
        evidence_refs=("evidence://action-worker-observation",),
        observed_at=proof.checkpointed_at + timedelta(seconds=1),
        recorded_at=proof.checkpointed_at + timedelta(seconds=2),
        confidence=1.0,
    )
    ledger = append_blackboard_entry(
        ledger=ledger,
        entry=action,
        registry=_registry(),
        topology=_topology(),
    )
    data = build_blackboard_entry(
        entry_id="data-observation-1",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref="colony://data",
        worker_id="worker-data",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
        subject_ref="inventory://store/fulya",
        artifact_ref="artifact://inventory/observation-1",
        evidence_refs=("evidence://inventory-live-read",),
        observed_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        confidence=0.99,
    )
    ledger = append_blackboard_entry(
        ledger=ledger,
        entry=data,
        registry=_registry(),
        topology=_topology(),
    )
    return ledger, action, data


def _claims(action, data):
    return (
        ColonyEvidenceClaimBinding(
            entry_id=action.entry_id,
            entry_fingerprint=action.fingerprint,
            proposition_ref=f"action-applied://{ACTION_ID}",
            stance=ColonyEvidenceStance.SUPPORTS,
        ),
        ColonyEvidenceClaimBinding(
            entry_id=data.entry_id,
            entry_fingerprint=data.fingerprint,
            proposition_ref="inventory-state://observation-available",
            stance=ColonyEvidenceStance.SUPPORTS,
        ),
    )


def test_raw_action_result_remains_fail_closed_without_verified_action_bridge():
    proof = _proof()
    ledger, action, data = _ledger_with_action_and_data(proof)
    bundle = verify_colony_evidence(
        ledger=ledger,
        policy=_policy(),
        review=_review(),
        claims=_claims(action, data),
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=1),
    )
    assert bundle.status is ColonyEvidenceStatus.INSUFFICIENT
    assert "colony_fanin_action_result_requires_verified_action_bridge" in bundle.blockers
    assert build_executive_synthesis_candidate(bundle).status is ExecutiveSynthesisStatus.BLOCKED


def test_strong_verified_action_proof_upgrades_action_result_through_existing_fanin():
    proof = _proof()
    ledger, action, data = _ledger_with_action_and_data(proof)
    binding = bind_verified_action_result(
        entry=action,
        proof=proof,
        registry=_registry(),
        topology=_topology(),
        bound_at=proof.checkpointed_at + timedelta(seconds=3),
    )
    bundle = verify_colony_evidence_with_verified_actions(
        ledger=ledger,
        policy=_policy(),
        review=_review(),
        claims=_claims(action, data),
        verified_action_bindings={action.entry_id: binding},
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=1),
    )
    assert bundle.status is ColonyEvidenceStatus.VERIFIED
    assert bundle.producer_colony_refs == ("colony://action", "colony://data")
    assert f"verified-action-proof://{proof.fingerprint}" in bundle.artifact_refs
    assert proof.transaction_ref in bundle.grounded_evidence_refs
    assert "evidence://authoritative-readback" in bundle.grounded_evidence_refs
    assert bundle.truth_authority_granted is False
    assert bundle.causal_claim_proven is False
    assert bundle.execution_authority_granted is False
    assert build_executive_synthesis_candidate(bundle).status is ExecutiveSynthesisStatus.READY


def test_verified_action_cannot_support_arbitrary_business_proposition():
    proof = _proof()
    ledger, action, data = _ledger_with_action_and_data(proof)
    binding = bind_verified_action_result(
        entry=action,
        proof=proof,
        registry=_registry(),
        topology=_topology(),
        bound_at=proof.checkpointed_at + timedelta(seconds=3),
    )
    claims = list(_claims(action, data))
    claims[0] = claims[0].model_copy(update={"proposition_ref": "business://sales-will-increase"})
    with pytest.raises(ValueError, match="colony_verified_action_fanin_proposition_scope_mismatch"):
        verify_colony_evidence_with_verified_actions(
            ledger=ledger,
            policy=_policy(),
            review=_review(),
            claims=tuple(claims),
            verified_action_bindings={action.entry_id: binding},
            registry=_registry(),
            topology=_topology(),
            as_of=NOW + timedelta(minutes=1),
        )


def test_verified_action_claim_cannot_refute_its_own_canonical_applied_proof():
    proof = _proof()
    ledger, action, data = _ledger_with_action_and_data(proof)
    binding = bind_verified_action_result(
        entry=action,
        proof=proof,
        registry=_registry(),
        topology=_topology(),
        bound_at=proof.checkpointed_at + timedelta(seconds=3),
    )
    claims = list(_claims(action, data))
    claims[0] = claims[0].model_copy(update={"stance": ColonyEvidenceStance.REFUTES})
    with pytest.raises(ValueError, match="colony_verified_action_fanin_verified_action_must_support"):
        verify_colony_evidence_with_verified_actions(
            ledger=ledger,
            policy=_policy(),
            review=_review(),
            claims=tuple(claims),
            verified_action_bindings={action.entry_id: binding},
            registry=_registry(),
            topology=_topology(),
            as_of=NOW + timedelta(minutes=1),
        )


def test_late_verified_action_binding_cannot_leak_into_historical_fanin():
    proof = _proof()
    ledger, action, data = _ledger_with_action_and_data(proof)
    binding = bind_verified_action_result(
        entry=action,
        proof=proof,
        registry=_registry(),
        topology=_topology(),
        bound_at=NOW + timedelta(minutes=10),
    )
    bundle = verify_colony_evidence_with_verified_actions(
        ledger=ledger,
        policy=_policy(),
        review=_review(),
        claims=_claims(action, data),
        verified_action_bindings={action.entry_id: binding},
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=1),
    )
    assert bundle.status is ColonyEvidenceStatus.INSUFFICIENT
    assert "colony_fanin_action_result_requires_verified_action_bridge" in bundle.blockers


def test_action_result_subject_and_proof_reference_are_exactly_bound():
    proof = _proof()
    ledger, action, _ = _ledger_with_action_and_data(proof)
    wrong_subject = action.model_copy(update={"subject_ref": "action://different-action"})
    with pytest.raises(ValueError, match="swarm_blackboard_entry_fingerprint_mismatch"):
        bind_verified_action_result(
            entry=wrong_subject,
            proof=proof,
            registry=_registry(),
            topology=_topology(),
            bound_at=NOW + timedelta(minutes=1),
        )

    wrong_ref = action.model_copy(update={"artifact_ref": "verified-action-proof://" + "0" * 64})
    with pytest.raises(ValueError, match="swarm_blackboard_entry_fingerprint_mismatch"):
        bind_verified_action_result(
            entry=wrong_ref,
            proof=proof,
            registry=_registry(),
            topology=_topology(),
            bound_at=NOW + timedelta(minutes=1),
        )


def test_tampered_strong_action_proof_is_revalidated_before_bridge():
    proof = _proof()
    _, action, _ = _ledger_with_action_and_data(proof)
    tampered = proof.model_copy(update={"capability_ref": "capability://inventory.delete"})
    with pytest.raises(ValueError, match="timeline_verified_action_proof_fingerprint_mismatch"):
        bind_verified_action_result(
            entry=action,
            proof=tampered,
            registry=_registry(),
            topology=_topology(),
            bound_at=NOW + timedelta(minutes=1),
        )


def test_unreferenced_verified_action_binding_is_rejected_not_silently_injected():
    proof = _proof()
    ledger, action, data = _ledger_with_action_and_data(proof)
    binding = bind_verified_action_result(
        entry=action,
        proof=proof,
        registry=_registry(),
        topology=_topology(),
        bound_at=proof.checkpointed_at + timedelta(seconds=3),
    )
    data_only_claim = (
        ColonyEvidenceClaimBinding(
            entry_id=data.entry_id,
            entry_fingerprint=data.fingerprint,
            proposition_ref="inventory-state://observation-available",
            stance=ColonyEvidenceStance.SUPPORTS,
        ),
    )
    with pytest.raises(ValueError, match="colony_verified_action_fanin_unreferenced_binding_forbidden"):
        verify_colony_evidence_with_verified_actions(
            ledger=ledger,
            policy=_policy(),
            review=_review(),
            claims=data_only_claim,
            verified_action_bindings={action.entry_id: binding},
            registry=_registry(),
            topology=_topology(),
            as_of=NOW + timedelta(minutes=1),
        )
