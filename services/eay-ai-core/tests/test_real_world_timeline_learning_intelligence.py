import json
from datetime import datetime, timedelta, timezone

import pytest

from app.device_world_model import DeviceCapability, DeviceClass, DeviceNode, DeviceTrust, DeviceWorldSnapshot
from app.mission_execution import CapabilityExecutionOutcome, MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint, record_step_result
from app.outcome_learning import DecisionLearningRecord, ExpectedMetricOutcome, GovernedActionReceipt, ObservedMetricOutcome
from app.playwright_mission_adapter import BrowserEffectVerification, EffectVerificationStatus
from app.real_world_timeline import TimelineAuthorityClass, TimelineEventKind, TimelineRelationKind, build_real_world_timeline
from app.real_world_timeline_learning import (
    action_executes_decision_link,
    build_verified_mission_action_proof,
    decision_learning_event,
    device_world_snapshot_events,
    outcome_follows_action_link,
    verified_action_event,
    verified_metric_outcome_event,
)
from app.world_model import TruthClass, WorldAssertion

NOW = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)


def _decision():
    return DecisionLearningRecord(
        decision_id="decision-fulya-stock",
        tenant_id="YS_TR",
        decided_at=NOW,
        decision_type="inventory_recovery",
        recommendation_ref="decision://fulya-stock/replenish",
        expected_outcomes=(ExpectedMetricOutcome(
            metric_key="stock_gap",
            baseline_value=987654.321,
            expected_value=123456.789,
            unit="units",
            confidence=0.91,
            evidence_refs=("evidence://forecast",),
        ),),
        decision_evidence_refs=("evidence://decision",),
    )


def _action_bundle(*, verification_status=EffectVerificationStatus.VERIFIED_APPLIED):
    step = MissionStep(
        step_id="adjust-stock",
        description="Apply the authorized stock adjustment",
        side_effect=True,
        idempotency_key="opaque-idempotency-key",
        effect_verifier_ref="capability://inventory.readback",
    )
    definition = MissionDefinition(
        mission_id="mission-fulya-stock",
        objective="Correct verified inventory state",
        tenant_id="YS_TR",
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="adjust-stock",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref="capability://inventory.adjust",
    )
    transaction_ref = "transaction://inventory/123"
    verification = BrowserEffectVerification(
        status=verification_status,
        evidence_refs=("evidence://authoritative-readback",),
        transaction_ref=transaction_ref,
    )
    outcome = CapabilityExecutionOutcome(
        succeeded=True,
        effect_verified=True,
        evidence_refs=("evidence://browser-receipt", "evidence://authoritative-readback"),
        transaction_ref=transaction_ref,
    )
    checkpoint = record_step_result(
        definition,
        new_checkpoint(definition, now=NOW - timedelta(seconds=2)),
        step_id="adjust-stock",
        succeeded=True,
        evidence_refs=("evidence://browser-receipt", "evidence://authoritative-readback", transaction_ref),
        now=NOW + timedelta(seconds=10),
    )
    receipt = GovernedActionReceipt(
        action_id="action-stock-adjustment",
        decision_id="decision-fulya-stock",
        tenant_id="YS_TR",
        executed_at=NOW + timedelta(seconds=3),
        capability_ref="capability://inventory.adjust",
        effect_verified=True,
        evidence_refs=("evidence://browser-receipt", "evidence://authoritative-readback"),
    )
    return definition, checkpoint, spec, outcome, verification, receipt


def _authoritative_outcome():
    observed_at = NOW + timedelta(minutes=30)
    assertion = WorldAssertion(
        assertion_id="assertion-stock-gap-outcome",
        tenant_id="YS_TR",
        entity_id="store:fulya",
        field_name="stock_gap",
        value=432198.765,
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        valid_from=observed_at - timedelta(minutes=1),
        observed_at=observed_at,
        source_ref="bq://curated/inventory",
        evidence_ref="evidence://live-stock-gap",
        confidence=0.99,
    )
    outcome = ObservedMetricOutcome(
        metric_key="stock_gap",
        observed_value=432198.765,
        unit="units",
        observed_at=observed_at,
        governed_truth_ref="evidence://live-stock-gap",
        evidence_refs=("evidence://live-stock-gap",),
    )
    return assertion, outcome


def test_decision_event_does_not_copy_expected_numeric_payload():
    event = decision_learning_event(_decision())
    payload = json.dumps(event.model_dump(mode="json"), sort_keys=True)
    assert event.event_kind is TimelineEventKind.DECISION
    assert event.authority_class is TimelineAuthorityClass.DECISION_RECORD
    assert "987654.321" not in payload
    assert "123456.789" not in payload
    assert event.execution_authority_granted is False
    assert event.causal_claim_proven is False


def test_boolean_only_action_receipt_cannot_be_upgraded_without_authoritative_verification():
    definition, checkpoint, spec, outcome, verification, receipt = _action_bundle(
        verification_status=EffectVerificationStatus.UNKNOWN
    )
    with pytest.raises(ValueError, match="timeline_verified_action_requires_authoritative_applied_verification"):
        build_verified_mission_action_proof(
            receipt=receipt,
            definition=definition,
            checkpoint=checkpoint,
            spec=spec,
            execution_outcome=outcome,
            verification=verification,
        )


def test_verified_action_binds_checkpoint_readback_and_transaction_evidence():
    definition, checkpoint, spec, outcome, verification, receipt = _action_bundle()
    proof = build_verified_mission_action_proof(
        receipt=receipt,
        definition=definition,
        checkpoint=checkpoint,
        spec=spec,
        execution_outcome=outcome,
        verification=verification,
    )
    event = verified_action_event(proof)
    assert event.event_kind is TimelineEventKind.ACTION
    assert event.authority_class is TimelineAuthorityClass.VERIFIED_ACTION
    assert "evidence://authoritative-readback" in event.evidence_refs
    assert "transaction://inventory/123" in event.evidence_refs
    assert event.execution_authority_granted is False
    assert event.causal_claim_proven is False


def test_tampered_verified_action_proof_is_rejected():
    definition, checkpoint, spec, outcome, verification, receipt = _action_bundle()
    proof = build_verified_mission_action_proof(
        receipt=receipt,
        definition=definition,
        checkpoint=checkpoint,
        spec=spec,
        execution_outcome=outcome,
        verification=verification,
    )
    tampered = proof.model_copy(update={"capability_ref": "capability://inventory.delete"})
    with pytest.raises(ValueError, match="timeline_verified_action_proof_fingerprint_mismatch"):
        verified_action_event(tampered)


def test_verified_metric_outcome_keeps_numeric_value_in_canonical_world_truth():
    assertion, outcome = _authoritative_outcome()
    event = verified_metric_outcome_event(
        outcome=outcome,
        tenant_id="YS_TR",
        assertion=assertion,
        decision_id="decision-fulya-stock",
        action_id="action-stock-adjustment",
    )
    payload = json.dumps(event.model_dump(mode="json"), sort_keys=True)
    assert event.event_kind is TimelineEventKind.OUTCOME
    assert event.authority_class is TimelineAuthorityClass.VERIFIED_OUTCOME
    assert "432198.765" not in payload
    assert event.data_ref == "world-assertion://assertion-stock-gap-outcome"
    assert event.causal_claim_proven is False


def test_analytic_inference_cannot_be_promoted_to_verified_outcome():
    assertion, outcome = _authoritative_outcome()
    assertion = assertion.model_copy(update={"truth_class": TruthClass.ANALYTIC_INFERENCE})
    with pytest.raises(ValueError, match="timeline_outcome_requires_authoritative_world_truth"):
        verified_metric_outcome_event(outcome=outcome, tenant_id="YS_TR", assertion=assertion)


def test_device_world_is_observation_only_and_does_not_copy_transport_refs():
    node = DeviceNode(
        device_ref="meeting-display-01",
        tenant_ref="YS_TR",
        device_class=DeviceClass.MEETING_DISPLAY,
        trust=DeviceTrust.ATTESTED,
        identity_evidence_ref="evidence://device-attestation",
        capabilities=frozenset({DeviceCapability.PRESENT_DASHBOARD}),
        transport_refs=("transport://private-lan/session-opaque",),
        room_ref="room:hq-boardroom",
        online=True,
        observed_at=NOW - timedelta(seconds=5),
        attestation_expires_at=NOW + timedelta(minutes=5),
    )
    snapshot = DeviceWorldSnapshot(
        tenant_ref="YS_TR",
        observed_at=NOW,
        devices=(node,),
        source_evidence_refs=("evidence://device-discovery",),
    )
    event = device_world_snapshot_events(snapshot)[0]
    payload = json.dumps(event.model_dump(mode="json"), sort_keys=True)
    assert event.event_kind is TimelineEventKind.DEVICE_OBSERVATION
    assert event.authority_class is TimelineAuthorityClass.DEVICE_OBSERVATION
    assert "transport://private-lan/session-opaque" not in payload
    assert event.execution_authority_granted is False
    assert event.timeline_grants_truth_authority is False


def test_outcome_cannot_link_before_action():
    definition, checkpoint, spec, execution_outcome, verification, receipt = _action_bundle()
    proof = build_verified_mission_action_proof(
        receipt=receipt,
        definition=definition,
        checkpoint=checkpoint,
        spec=spec,
        execution_outcome=execution_outcome,
        verification=verification,
    )
    action = verified_action_event(proof)
    assertion, observed = _authoritative_outcome()
    observed = observed.model_copy(update={"observed_at": NOW + timedelta(seconds=1)})
    assertion = assertion.model_copy(update={"valid_from": NOW, "observed_at": NOW + timedelta(seconds=1)})
    outcome = verified_metric_outcome_event(
        outcome=observed,
        tenant_id="YS_TR",
        assertion=assertion,
        action_id="action-stock-adjustment",
    )
    with pytest.raises(ValueError, match="timeline_outcome_cannot_precede_action"):
        outcome_follows_action_link(outcome=outcome, action=action)


def test_decision_action_outcome_chain_is_evidence_graph_not_causal_proof():
    decision = decision_learning_event(_decision())
    definition, checkpoint, spec, execution_outcome, verification, receipt = _action_bundle()
    proof = build_verified_mission_action_proof(
        receipt=receipt,
        definition=definition,
        checkpoint=checkpoint,
        spec=spec,
        execution_outcome=execution_outcome,
        verification=verification,
    )
    action = verified_action_event(proof)
    assertion, observed = _authoritative_outcome()
    outcome = verified_metric_outcome_event(
        outcome=observed,
        tenant_id="YS_TR",
        assertion=assertion,
        decision_id="decision-fulya-stock",
        action_id="action-stock-adjustment",
    )
    action_link = action_executes_decision_link(action=action, decision=decision)
    outcome_link = outcome_follows_action_link(outcome=outcome, action=action)
    timeline = build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=NOW - timedelta(minutes=1),
        window_end=NOW + timedelta(hours=1),
        events=(decision, action, outcome),
        links=(action_link, outcome_link),
    )
    assert [item.event_kind for item in timeline.events] == [
        TimelineEventKind.DECISION,
        TimelineEventKind.ACTION,
        TimelineEventKind.OUTCOME,
    ]
    assert {link.relation for link in timeline.links} == {
        TimelineRelationKind.ACTION_EXECUTES_DECISION,
        TimelineRelationKind.OUTCOME_FOLLOWS_ACTION,
    }
    assert all(link.causal_claim_proven is False for link in timeline.links)
    assert timeline.authoritative_truth_surface is False
    assert timeline.execution_authority_surface is False
    assert timeline.causal_proof_surface is False
