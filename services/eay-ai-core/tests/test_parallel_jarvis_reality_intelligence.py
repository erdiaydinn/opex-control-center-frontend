from datetime import datetime, timedelta, timezone

import pytest

from app.ambient_context_intelligence import AmbientModality, AmbientSemanticSignal
from app.live_company_reality import (
    LiveEvidenceClass,
    LiveSourceBindingPolicy,
    LiveSourceKind,
    build_live_source_attestation,
)
from app.live_company_source_runtime import (
    ReadOnlySourceBatch,
    ReadOnlySourceField,
    ReadOnlySourcePlan,
    collect_read_only_source,
    promote_verified_read_only_batch,
)
from app.meeting_context_intelligence import (
    MeetingContextPolicy,
    MeetingDiarizationSignal,
    MeetingMomentKind,
    MeetingWatchRule,
    derive_meeting_candidate,
    evaluate_meeting_watch,
    meeting_signal_from_ambient,
)
from app.physical_capability_gateway import (
    PhysicalAction,
    PhysicalRisk,
    make_physical_request,
)
from app.physical_simulation_runtime import (
    PhysicalSimulationPolicy,
    SimulationFidelity,
    build_physical_simulation_evidence,
    evaluate_physical_simulation_gate,
)
from app.world_model import TruthClass

NOW = datetime(2026, 8, 19, 0, 0, tzinfo=timezone.utc)


class InventoryReadAdapter:
    def collect(self, plan: ReadOnlySourcePlan) -> ReadOnlySourceBatch:
        return ReadOnlySourceBatch(
            binding_id=plan.binding_id,
            tenant_id=plan.tenant_id,
            source_kind=plan.source_kind,
            source_ref=plan.source_ref,
            schema_contract=plan.schema_contract,
            schema_version=plan.schema_version,
            environment_ref=plan.environment_ref,
            execution_identity_ref=plan.execution_identity_ref,
            operation_ref=plan.operation_ref,
            observed_at=NOW + timedelta(seconds=2),
            source_receipt_ref="source-receipt://inventory/fulya/001",
            evidence_ref="evidence://inventory-read/001",
            fields=(
                ReadOnlySourceField(
                    entity_id="store:fulya",
                    field_name="inventory.stock_on_hand",
                    value=24,
                    valid_from=NOW,
                    confidence=0.99,
                ),
            ),
        )


def _inventory_policy() -> LiveSourceBindingPolicy:
    return LiveSourceBindingPolicy(
        binding_id="inventory-live-v1",
        tenant_id="YS_TR",
        source_kind=LiveSourceKind.INVENTORY,
        source_ref="company://inventory/authoritative",
        schema_contract="inventory-live",
        schema_version="1",
        environment_ref="environment://production",
        execution_identity_ref="identity://inventory-read-only",
        verifier_ref="verifier://inventory-independent-readback",
        truth_class=TruthClass.VERIFIED_COMPANY,
        max_observation_age_seconds=60,
        max_attestation_age_seconds=60,
        allowed_fields=("inventory.stock_on_hand",),
    )


def _inventory_plan() -> ReadOnlySourcePlan:
    return ReadOnlySourcePlan(
        binding_id="inventory-live-v1",
        tenant_id="YS_TR",
        source_kind=LiveSourceKind.INVENTORY,
        source_ref="company://inventory/authoritative",
        schema_contract="inventory-live",
        schema_version="1",
        environment_ref="environment://production",
        execution_identity_ref="identity://inventory-read-only",
        operation_ref="read://inventory/current-stock",
        requested_fields=("inventory.stock_on_hand",),
        requested_at=NOW,
    )


def test_read_only_collection_does_not_become_truth_without_attestation():
    collection = collect_read_only_source(
        plan=_inventory_plan(),
        policy=_inventory_policy(),
        adapter=InventoryReadAdapter(),
    )
    assert collection.truth_promoted is False
    assert collection.execution_authority_granted is False
    assert collection.batch.fields[0].value == 24


def test_read_only_live_batch_promotes_only_through_existing_authoritative_gate():
    policy = _inventory_policy()
    collection = collect_read_only_source(
        plan=_inventory_plan(),
        policy=policy,
        adapter=InventoryReadAdapter(),
    )
    attestation = build_live_source_attestation(
        binding_id=policy.binding_id,
        tenant_id=policy.tenant_id,
        source_kind=policy.source_kind,
        source_ref=policy.source_ref,
        schema_contract=policy.schema_contract,
        schema_version=policy.schema_version,
        environment_ref=policy.environment_ref,
        execution_identity_ref=policy.execution_identity_ref,
        verifier_ref=policy.verifier_ref,
        verified_at=NOW + timedelta(seconds=3),
        evidence_ref="evidence://inventory-independent-readback/001",
        source_receipt_ref=collection.batch.source_receipt_ref,
        evidence_class=LiveEvidenceClass.AUTHORITATIVE_LIVE,
        field_production_verified=True,
    )
    result = promote_verified_read_only_batch(
        collection=collection,
        policy=policy,
        attestation=attestation,
        as_of=NOW + timedelta(seconds=5),
        known_entity_ids={"store:fulya"},
        trusted_attestation_fingerprints={attestation.fingerprint},
    )
    assert result.authoritative_assertion_count == 1
    assert result.outcomes[0].assertion is not None
    assert result.outcomes[0].assertion.value == 24
    assert result.execution_authority_granted is False


def test_read_only_source_plan_rejects_mutation_semantics():
    payload = _inventory_plan().model_dump()
    payload["mutation_requested"] = True
    with pytest.raises(ValueError, match="live_company_source_runtime_forbids_mutation"):
        ReadOnlySourcePlan(**payload)


def _ambient_meeting_signal() -> AmbientSemanticSignal:
    return AmbientSemanticSignal(
        signal_ref="ambient://meeting/segment-1",
        modality=AmbientModality.MICROPHONE,
        observed_at=NOW,
        application_ref="app://meeting",
        semantic_tags=frozenset({"risk", "fulya", "decision_candidate"}),
        confidence=0.94,
        observation_seconds=8.0,
        local_processing=True,
        content_ref="evidence://meeting-semantic/segment-1",
    )


def test_meeting_diarization_is_context_not_identity_or_task_authority():
    signal = meeting_signal_from_ambient(
        ambient=_ambient_meeting_signal(),
        meeting_ref="meeting://ops-daily",
        session_ref="session://ops-daily/2026-08-19",
        speaker_cluster_ref="speaker-cluster://session/a",
        diarization_confidence=0.91,
        topic_refs=frozenset({"topic://fulya-risk"}),
    )
    candidate = derive_meeting_candidate(
        signal=signal,
        policy=MeetingContextPolicy(enabled=True),
    )
    assert candidate.kind is MeetingMomentKind.DECISION_CANDIDATE
    assert candidate.speaker_identity_resolved is False
    assert candidate.task_creation_allowed is False
    assert candidate.execution_authority_granted is False

    rule = MeetingWatchRule(
        rule_ref="rule://fulya-risk",
        meeting_refs=frozenset({"meeting://ops-daily"}),
        required_tags=frozenset({"risk"}),
        required_topic_refs=frozenset({"topic://fulya-risk"}),
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(hours=1),
    )
    decision = evaluate_meeting_watch(candidate=candidate, rule=rule, now=NOW)
    assert decision.matched is True
    assert decision.notification_eligible is True
    assert decision.task_creation_allowed is False
    assert decision.execution_authority_granted is False


def test_meeting_speaker_cluster_cannot_claim_identity():
    with pytest.raises(ValueError, match="meeting_diarization_cluster_is_not_identity"):
        MeetingDiarizationSignal(
            meeting_ref="meeting://ops-daily",
            session_ref="session://ops-daily/2026-08-19",
            speaker_cluster_ref="speaker-cluster://session/a",
            observed_at=NOW,
            segment_seconds=5.0,
            diarization_confidence=0.95,
            semantic_tags=frozenset({"risk"}),
            evidence_refs=("evidence://semantic",),
            speaker_identity_claimed=True,
        )


def _robot_request():
    return make_physical_request(
        request_ref="physical-request://robot/pick-1",
        tenant_ref="YS_TR",
        principal_ref="principal://erdi",
        identity_evidence_ref="identity-evidence://oidc/session-1",
        device_ref="robot://lab/arm-1",
        action=PhysicalAction.ROBOTIC_ACTUATION,
        risk=PhysicalRisk.CRITICAL,
        requested_at=NOW,
        payload_ref="payload://robot/pick-plan/1",
        payload_digest="a" * 64,
    )


def test_robotic_action_requires_hardware_in_loop_but_simulation_never_authorizes_execution():
    request = _robot_request()
    evidence = build_physical_simulation_evidence(
        request=request,
        simulator_ref="simulator://ros/hil-1",
        scenario_ref="scenario://pick-safe-box",
        fidelity=SimulationFidelity.HARDWARE_IN_LOOP,
        started_at=NOW + timedelta(seconds=1),
        completed_at=NOW + timedelta(seconds=3),
        safety_invariants_checked=("workspace_bounds", "force_limit", "collision_check"),
        collision_free=True,
        estimated_effect_ref="simulation-effect://pick-safe-box/1",
        evidence_refs=("evidence://ros-hil/run-1",),
    )
    gate = evaluate_physical_simulation_gate(
        request=request,
        evidence=evidence,
        policy=PhysicalSimulationPolicy(),
        now=NOW + timedelta(seconds=5),
    )
    assert gate.eligible_for_physical_preflight is True
    assert gate.execution_authority_granted is False


def test_robotic_digital_twin_alone_is_not_enough_for_default_critical_gate():
    request = _robot_request()
    evidence = build_physical_simulation_evidence(
        request=request,
        simulator_ref="simulator://ros/digital-twin",
        scenario_ref="scenario://pick-safe-box",
        fidelity=SimulationFidelity.DIGITAL_TWIN,
        started_at=NOW + timedelta(seconds=1),
        completed_at=NOW + timedelta(seconds=3),
        safety_invariants_checked=("workspace_bounds", "force_limit", "collision_check"),
        collision_free=True,
        estimated_effect_ref="simulation-effect://pick-safe-box/1",
        evidence_refs=("evidence://ros-sim/run-1",),
    )
    gate = evaluate_physical_simulation_gate(
        request=request,
        evidence=evidence,
        policy=PhysicalSimulationPolicy(),
        now=NOW + timedelta(seconds=5),
    )
    assert gate.eligible_for_physical_preflight is False
    assert "physical_simulation_fidelity_insufficient" in gate.blockers


def test_tampered_physical_simulation_evidence_fails_closed():
    request = _robot_request()
    evidence = build_physical_simulation_evidence(
        request=request,
        simulator_ref="simulator://ros/hil-1",
        scenario_ref="scenario://pick-safe-box",
        fidelity=SimulationFidelity.HARDWARE_IN_LOOP,
        started_at=NOW + timedelta(seconds=1),
        completed_at=NOW + timedelta(seconds=3),
        safety_invariants_checked=("workspace_bounds", "force_limit", "collision_check"),
        collision_free=True,
        estimated_effect_ref="simulation-effect://pick-safe-box/1",
        evidence_refs=("evidence://ros-hil/run-1",),
    )
    tampered = evidence.model_copy(update={"device_ref": "robot://lab/arm-evil"})
    gate = evaluate_physical_simulation_gate(
        request=request,
        evidence=tampered,
        policy=PhysicalSimulationPolicy(),
        now=NOW + timedelta(seconds=5),
    )
    assert gate.eligible_for_physical_preflight is False
    assert gate.blockers == ("physical_simulation_evidence_invalid",)
