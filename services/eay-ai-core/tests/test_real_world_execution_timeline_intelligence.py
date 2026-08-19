from datetime import datetime, timedelta, timezone

import pytest

from app.device_world_model import (
    DeviceCapability,
    DeviceClass,
    DeviceNode,
    DeviceTrust,
    DeviceWorldSnapshot,
)
from app.outcome_learning import (
    DecisionLearningRecord,
    ExpectedMetricOutcome,
    GovernedActionReceipt,
    ObservedMetricOutcome,
)
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineRelationKind,
    build_real_world_timeline,
)
from app.real_world_timeline_adapters import (
    timeline_event_from_decision_record,
    timeline_event_from_observed_outcome,
    timeline_event_from_verified_action_receipt,
    timeline_events_from_device_world_snapshot,
    timeline_links_for_decision_action_outcomes,
)


NOW = datetime(2026, 8, 19, 7, 0, tzinfo=timezone.utc)


def _decision(*, tenant_id: str = "YS_TR") -> DecisionLearningRecord:
    return DecisionLearningRecord(
        decision_id="decision-otp-fulya-001",
        tenant_id=tenant_id,
        decided_at=NOW,
        decision_type="capacity_adjustment",
        recommendation_ref="decision://otp/fulya/capacity-adjustment",
        expected_outcomes=(
            ExpectedMetricOutcome(
                metric_key="ops.otp",
                baseline_value=91.2,
                expected_value=94.0,
                unit="pct",
                confidence=0.84,
                evidence_refs=("evidence://forecast/otp/fulya",),
            ),
        ),
        decision_evidence_refs=("live-truth-readiness://YS_TR/otp/proceed/abc123",),
    )


def _action(
    *,
    tenant_id: str = "YS_TR",
    effect_verified: bool = True,
    executed_at: datetime | None = None,
) -> GovernedActionReceipt:
    return GovernedActionReceipt(
        action_id="action-capacity-fulya-001",
        decision_id="decision-otp-fulya-001",
        tenant_id=tenant_id,
        executed_at=executed_at or NOW + timedelta(minutes=5),
        capability_ref="capability://workforce/capacity-adjustment/v1",
        effect_verified=effect_verified,
        approval_ref="approval://ops-manager/fulya/001",
        evidence_refs=("effect-verification://capacity/fulya/001",),
    )


def _outcome(*, observed_at: datetime | None = None) -> ObservedMetricOutcome:
    return ObservedMetricOutcome(
        metric_key="ops.otp",
        observed_value=93.6,
        unit="pct",
        observed_at=observed_at or NOW + timedelta(hours=1),
        governed_truth_ref="company-truth://otp/fulya/19082026T0800Z",
        evidence_refs=("evidence://otp/fulya/observed",),
    )


def test_decision_event_keeps_expected_values_out_of_timeline_payload() -> None:
    event = timeline_event_from_decision_record(_decision())
    encoded = event.model_dump_json()

    assert event.event_kind is TimelineEventKind.DECISION
    assert event.authority_class is TimelineAuthorityClass.DECISION_RECORD
    assert event.timeline_grants_truth_authority is False
    assert event.execution_authority_granted is False
    assert "baseline_value" not in encoded
    assert "expected_value" not in encoded
    assert "recommendation_ref" not in encoded


def test_unverified_action_cannot_be_promoted_to_verified_timeline_action() -> None:
    with pytest.raises(ValueError, match="timeline_action_requires_verified_effect"):
        timeline_event_from_verified_action_receipt(
            action=_action(effect_verified=False),
            decision=_decision(),
        )


def test_verified_decision_action_outcome_chain_is_indexed_without_causal_claim() -> None:
    decision = _decision()
    action = _action()
    outcome = _outcome()

    decision_event = timeline_event_from_decision_record(decision)
    action_event = timeline_event_from_verified_action_receipt(
        action=action,
        decision=decision,
    )
    outcome_event = timeline_event_from_observed_outcome(
        decision=decision,
        action=action,
        outcome=outcome,
    )
    links = timeline_links_for_decision_action_outcomes(
        decision_event=decision_event,
        action_event=action_event,
        outcome_events=(outcome_event,),
    )
    snapshot = build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=NOW - timedelta(minutes=1),
        window_end=NOW + timedelta(hours=2),
        events=(decision_event, action_event, outcome_event),
        links=links,
    )

    assert tuple(item.event_kind for item in snapshot.events) == (
        TimelineEventKind.DECISION,
        TimelineEventKind.ACTION,
        TimelineEventKind.OUTCOME,
    )
    assert {item.relation for item in snapshot.links} == {
        TimelineRelationKind.ACTION_EXECUTES_DECISION,
        TimelineRelationKind.OUTCOME_FOLLOWS_ACTION,
    }
    assert all(item.causal_claim_proven is False for item in snapshot.links)
    assert snapshot.causal_proof_surface is False
    assert outcome_event.authority_class is TimelineAuthorityClass.VERIFIED_OUTCOME
    assert "observed_value" not in outcome_event.model_dump_json()


def test_outcome_before_verified_action_is_rejected() -> None:
    decision = _decision()
    action = _action(executed_at=NOW + timedelta(minutes=20))
    outcome = _outcome(observed_at=NOW + timedelta(minutes=10))

    with pytest.raises(ValueError, match="timeline_outcome_precedes_verified_action"):
        timeline_event_from_observed_outcome(
            decision=decision,
            action=action,
            outcome=outcome,
        )


def test_cross_tenant_action_cannot_bind_to_decision() -> None:
    with pytest.raises(ValueError, match="timeline_action_decision_identity_mismatch"):
        timeline_event_from_verified_action_receipt(
            action=_action(tenant_id="DE"),
            decision=_decision(tenant_id="YS_TR"),
        )


def test_outcome_metric_must_be_declared_by_decision() -> None:
    outcome = ObservedMetricOutcome(
        metric_key="ops.nsfr",
        observed_value=1.4,
        unit="pct",
        observed_at=NOW + timedelta(hours=1),
        governed_truth_ref="company-truth://nsfr/fulya/19082026T0800Z",
        evidence_refs=("evidence://nsfr/fulya/observed",),
    )

    with pytest.raises(ValueError, match="timeline_outcome_metric_not_declared_by_decision"):
        timeline_event_from_observed_outcome(
            decision=_decision(),
            outcome=outcome,
        )


def _device_snapshot(*, snapshot_at: datetime = NOW, device_at: datetime | None = None) -> DeviceWorldSnapshot:
    return DeviceWorldSnapshot(
        tenant_ref="YS_TR",
        observed_at=snapshot_at,
        devices=(
            DeviceNode(
                device_ref="device:meeting-display-7",
                tenant_ref="YS_TR",
                device_class=DeviceClass.MEETING_DISPLAY,
                trust=DeviceTrust.ATTESTED,
                identity_evidence_ref="device-attestation://meeting-display-7/001",
                capabilities=frozenset(
                    {
                        DeviceCapability.DISPLAY_ARTIFACT,
                        DeviceCapability.PRESENT_DASHBOARD,
                    }
                ),
                transport_refs=(
                    "grpc://private-device-router.internal:443?token=must-not-copy",
                ),
                room_ref="room:istanbul-hq-7",
                online=True,
                observed_at=device_at or NOW - timedelta(seconds=5),
                attestation_expires_at=NOW + timedelta(minutes=15),
            ),
        ),
        source_evidence_refs=("mdm://snapshot/istanbul-hq/001",),
    )


def test_device_snapshot_indexes_observation_without_transport_material_or_authority() -> None:
    event = timeline_events_from_device_world_snapshot(_device_snapshot())[0]
    encoded = event.model_dump_json()

    assert event.event_kind is TimelineEventKind.DEVICE_OBSERVATION
    assert event.authority_class is TimelineAuthorityClass.DEVICE_OBSERVATION
    assert event.confidence == 0.98
    assert event.timeline_grants_truth_authority is False
    assert event.execution_authority_granted is False
    assert "private-device-router" not in encoded
    assert "must-not-copy" not in encoded
    assert "transport_refs" not in encoded
    assert "device:meeting-display-7" in encoded
    assert "room:istanbul-hq-7" in encoded


def test_device_snapshot_cannot_claim_observation_before_device_was_seen() -> None:
    with pytest.raises(ValueError, match="timeline_device_snapshot_precedes_device_observation"):
        timeline_events_from_device_world_snapshot(
            _device_snapshot(
                snapshot_at=NOW,
                device_at=NOW + timedelta(seconds=1),
            )
        )
