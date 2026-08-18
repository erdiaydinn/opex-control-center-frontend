from datetime import datetime, timedelta, timezone

import pytest

from app.ambient_context_intelligence import AmbientModality, AmbientSemanticSignal
from app.context_intelligence import (
    ContextKind,
    ContextSignal,
    ContextSourceClass,
    ImpactDimension,
)
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineEventLink,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    TimelineRelationKind,
    build_real_world_timeline,
    build_timeline_event,
    validate_timeline_event_integrity,
)
from app.real_world_timeline_adapters import (
    timeline_event_from_ambient_signal,
    timeline_event_from_context_signal,
    timeline_event_from_world_assertion,
)
from app.world_model import TruthClass, WorldAssertion


NOW = datetime(2026, 8, 18, 18, 0, tzinfo=timezone.utc)


def _object(ref: str = "store:fulya") -> TimelineObjectRelation:
    return TimelineObjectRelation(
        object_ref=ref,
        object_kind=TimelineObjectKind.WORLD_ENTITY,
        qualifier=TimelineObjectQualifier.SUBJECT,
    )


def _event(event_id: str, *, tenant_id: str = "YS_TR", at: datetime = NOW):
    return build_timeline_event(
        event_id=event_id,
        event_type="eay.company.assertion",
        event_kind=TimelineEventKind.COMPANY_ASSERTION,
        source_ref="bigquery://curated/orders",
        tenant_id=tenant_id,
        occurred_at=at,
        observed_at=at + timedelta(seconds=2),
        effective_from=at,
        data_ref=f"world-assertion://{event_id}",
        authority_class=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        confidence=0.99,
        object_relations=(_object(),),
        evidence_refs=(f"evidence://{event_id}",),
    )


def test_world_assertion_is_indexed_without_copying_business_value():
    assertion = WorldAssertion(
        assertion_id="orders-fulya-1800",
        tenant_id="YS_TR",
        entity_id="store:fulya",
        field_name="orders.current",
        value={"orders": 9123, "sensitive_marker": "DO_NOT_DUPLICATE"},
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        valid_from=NOW,
        observed_at=NOW + timedelta(seconds=5),
        source_ref="bigquery://curated_data_shared.orders",
        evidence_ref="live-schema://orders/verified",
        confidence=0.99,
    )

    event = timeline_event_from_world_assertion(assertion)
    encoded = event.model_dump_json()

    assert event.data_ref == "world-assertion://orders-fulya-1800"
    assert event.authority_class is TimelineAuthorityClass.GOVERNED_OPERATIONAL
    assert "DO_NOT_DUPLICATE" not in encoded
    assert "sensitive_marker" not in encoded
    assert event.timeline_grants_truth_authority is False
    assert event.execution_authority_granted is False


def test_external_context_stays_context_only_and_can_be_active_after_announcement():
    signal = ContextSignal(
        signal_id="istanbul-rain-2026-08-18",
        kind=ContextKind.WEATHER,
        title="Heavy rain expected in Istanbul",
        starts_at=NOW + timedelta(hours=1),
        ends_at=NOW + timedelta(hours=4),
        observed_at=NOW,
        locations=("İstanbul",),
        expected_impacts=(ImpactDimension.DEMAND, ImpactDimension.DELIVERY_SPEED),
        source_name="official-weather-provider",
        source_url="https://weather.example/evidence/istanbul-rain",
        source_class=ContextSourceClass.OFFICIAL,
        source_confidence=0.96,
    )
    event = timeline_event_from_context_signal(signal=signal, tenant_id="YS_TR")

    assert event.authority_class is TimelineAuthorityClass.CONTEXT_ONLY
    assert event.timeline_grants_truth_authority is False
    assert event.object_relations[0].object_ref == "location:istanbul"

    snapshot = build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=NOW + timedelta(hours=2),
        window_end=NOW + timedelta(hours=3),
        events=(event,),
    )
    assert tuple(item.event_id for item in snapshot.events) == (event.event_id,)


def test_historical_replay_cannot_see_evidence_observed_in_the_future():
    event = build_timeline_event(
        event_id="late-arriving-live-observation",
        event_type="eay.company.assertion",
        event_kind=TimelineEventKind.COMPANY_ASSERTION,
        source_ref="bigquery://inventory",
        tenant_id="YS_TR",
        occurred_at=NOW,
        observed_at=NOW + timedelta(hours=3),
        effective_from=NOW,
        data_ref="world-assertion://inventory/late",
        authority_class=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        confidence=0.95,
        object_relations=(_object(),),
        evidence_refs=("evidence://inventory/late",),
    )

    snapshot = build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=NOW + timedelta(hours=1),
        window_end=NOW + timedelta(hours=2),
        events=(event,),
    )
    assert snapshot.events == ()


def test_ambient_signal_is_ephemeral_context_not_instruction_or_authority():
    signal = AmbientSemanticSignal(
        signal_ref="ambient://meeting/fulya-risk",
        modality=AmbientModality.SYSTEM_AUDIO,
        observed_at=NOW,
        application_ref="app://teams",
        semantic_tags=frozenset({"Fulya", "CAPEX", "risk"}),
        confidence=0.91,
        observation_seconds=8.0,
        local_processing=True,
    )
    event = timeline_event_from_ambient_signal(signal=signal, tenant_id="YS_TR")
    encoded = event.model_dump_json()

    assert event.authority_class is TimelineAuthorityClass.AMBIENT_UNTRUSTED
    assert event.timeline_grants_truth_authority is False
    assert event.execution_authority_granted is False
    assert event.raw_content_retained is False
    assert "raw_transcript" not in encoded


def test_timeline_relation_can_correlate_but_never_prove_causality():
    first = _event("orders-change")
    second = _event("otp-change", at=NOW + timedelta(minutes=5))

    with pytest.raises(ValueError, match="timeline_link_cannot_assert_causality"):
        TimelineEventLink(
            tenant_id="YS_TR",
            source_event_id=first.event_id,
            relation=TimelineRelationKind.TEMPORALLY_CORRELATED,
            target_event_id=second.event_id,
            evidence_refs=("analysis://temporal-overlap",),
            confidence=0.82,
            causal_claim_proven=True,
        )


def test_cross_tenant_event_is_rejected_before_snapshot_creation():
    with pytest.raises(ValueError, match="timeline_cross_tenant_event_forbidden"):
        build_real_world_timeline(
            tenant_id="YS_TR",
            window_start=NOW - timedelta(minutes=1),
            window_end=NOW + timedelta(hours=1),
            events=(_event("foreign", tenant_id="DE"),),
        )


def test_same_event_id_with_changed_fingerprint_fails_closed():
    first = _event("duplicate")
    second = build_timeline_event(
        event_id="duplicate",
        event_type="eay.company.assertion",
        event_kind=TimelineEventKind.COMPANY_ASSERTION,
        source_ref="bigquery://curated/orders",
        tenant_id="YS_TR",
        occurred_at=NOW,
        observed_at=NOW + timedelta(seconds=2),
        effective_from=NOW,
        data_ref="world-assertion://duplicate-revised",
        authority_class=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        confidence=0.90,
        object_relations=(_object(),),
        evidence_refs=("evidence://duplicate/revised",),
    )

    with pytest.raises(ValueError, match="timeline_event_id_conflict"):
        build_real_world_timeline(
            tenant_id="YS_TR",
            window_start=NOW - timedelta(minutes=1),
            window_end=NOW + timedelta(hours=1),
            events=(first, second),
        )


def test_model_copy_tampering_is_rejected_at_integrity_boundary():
    event = _event("tamper-me")
    tampered = event.model_copy(
        update={"authority_class": TimelineAuthorityClass.VERIFIED_COMPANY}
    )

    with pytest.raises(ValueError, match="timeline_event_fingerprint_mismatch"):
        validate_timeline_event_integrity(tampered)



def test_future_effective_company_assertion_is_indexed_when_observed_before_effective_date():
    assertion = WorldAssertion(
        assertion_id="future-company-policy",
        tenant_id="YS_TR",
        entity_id="company:eay",
        field_name="policy.future_effective",
        value=True,
        truth_class=TruthClass.VERIFIED_COMPANY,
        valid_from=NOW + timedelta(days=2),
        observed_at=NOW,
        source_ref="company-policy://approved-change",
        evidence_ref="evidence://policy/approved-change",
        confidence=1.0,
    )

    event = timeline_event_from_world_assertion(assertion)
    assert event.occurred_at == NOW
    assert event.effective_from == NOW + timedelta(days=2)

    snapshot = build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=NOW + timedelta(days=2),
        window_end=NOW + timedelta(days=3),
        events=(event,),
    )
    assert tuple(item.event_id for item in snapshot.events) == (event.event_id,)


def test_link_to_unknown_event_fails_instead_of_being_silently_dropped():
    event = _event("known")
    dangling = TimelineEventLink(
        tenant_id="YS_TR",
        source_event_id=event.event_id,
        relation=TimelineRelationKind.DERIVED_FROM,
        target_event_id="missing",
        evidence_refs=("evidence://link",),
        confidence=0.8,
    )

    with pytest.raises(ValueError, match="timeline_link_references_unknown_event"):
        build_real_world_timeline(
            tenant_id="YS_TR",
            window_start=NOW - timedelta(minutes=1),
            window_end=NOW + timedelta(hours=1),
            events=(event,),
            links=(dangling,),
        )

def test_secret_bearing_reference_is_rejected():
    with pytest.raises(ValueError, match="timeline_event_reference_may_contain_secret"):
        build_timeline_event(
            event_id="secret-ref",
            event_type="eay.external.context",
            event_kind=TimelineEventKind.EXTERNAL_CONTEXT,
            source_ref="https://provider.example/event?token=should-not-persist",
            tenant_id="YS_TR",
            occurred_at=NOW,
            observed_at=NOW,
            data_ref="context-signal://secret-ref",
            authority_class=TimelineAuthorityClass.CONTEXT_ONLY,
            confidence=0.8,
            object_relations=(
                TimelineObjectRelation(
                    object_ref="location:istanbul",
                    object_kind=TimelineObjectKind.LOCATION,
                    qualifier=TimelineObjectQualifier.AFFECTED,
                ),
            ),
            evidence_refs=("https://provider.example/evidence",),
        )
