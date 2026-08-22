from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.company_world_live_bridge import (
    CompanyMetricDirection,
    ContextCompanyLinkDisposition,
    ExternalContextDomain,
    GeographicScope,
    GeographicScopeLevel,
    assess_company_world_live_context,
    build_company_location_binding,
    build_company_metric_deviation,
    build_external_context_observation,
)
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.world_model import (
    EntityKind,
    TruthClass,
    WorldAssertion,
    WorldEntity,
    build_world_snapshot,
)

T0 = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
LOCATION = "store:fulya"


def company_world(
    *,
    as_of: datetime,
    orders_per_hour: float,
    tenant_id: str = "tenant-a",
    conflicting_value: float | None = None,
):
    entity = WorldEntity(
        entity_id=LOCATION,
        tenant_id=tenant_id,
        kind=EntityKind.STORE,
        display_name="Fulya",
    )
    assertions = [
        WorldAssertion(
            assertion_id=f"orders:{as_of.isoformat()}:a",
            tenant_id=tenant_id,
            entity_id=LOCATION,
            field_name="orders_per_hour",
            value=orders_per_hour,
            truth_class=TruthClass.GOVERNED_OPERATIONAL,
            valid_from=as_of - timedelta(hours=2),
            observed_at=as_of,
            source_ref="company://orders-live",
            evidence_ref=f"evidence://orders/{as_of.isoformat()}/a",
            confidence=0.99,
        )
    ]
    if conflicting_value is not None:
        assertions.append(
            WorldAssertion(
                assertion_id=f"orders:{as_of.isoformat()}:b",
                tenant_id=tenant_id,
                entity_id=LOCATION,
                field_name="orders_per_hour",
                value=conflicting_value,
                truth_class=TruthClass.GOVERNED_OPERATIONAL,
                valid_from=as_of - timedelta(hours=2),
                observed_at=as_of,
                source_ref="company://orders-live-second",
                evidence_ref=f"evidence://orders/{as_of.isoformat()}/b",
                confidence=0.99,
            )
        )
    return build_world_snapshot(
        tenant_id=tenant_id,
        as_of=as_of,
        entities=[entity],
        assertions=assertions,
    )


def fulya_scope() -> GeographicScope:
    return GeographicScope(
        level=GeographicScopeLevel.LOCATION,
        country_code="TR",
        region_key="istanbul",
        locality_key="sisli",
        location_ref=LOCATION,
    )


def locality_scope(locality: str = "sisli") -> GeographicScope:
    return GeographicScope(
        level=GeographicScopeLevel.LOCALITY,
        country_code="TR",
        region_key="istanbul",
        locality_key=locality,
    )


def binding(world):
    return build_company_location_binding(
        world=world,
        company_id="company-a",
        location_entity_id=LOCATION,
        scope=fulya_scope(),
        truth_class=TruthClass.VERIFIED_COMPANY,
        observed_at=world.as_of,
        evidence_ref="company-evidence://location/fulya",
    )


def external_event(
    *,
    event_id: str,
    authority: TimelineAuthorityClass = TimelineAuthorityClass.VERIFIED_EXTERNAL,
    tenant_id: str = "tenant-a",
    observed_at: datetime = T1,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
):
    return build_timeline_event(
        event_id=event_id,
        event_type="eay.external.context.observed",
        event_kind=TimelineEventKind.EXTERNAL_CONTEXT,
        source_ref=f"external-source://{event_id}",
        tenant_id=tenant_id,
        occurred_at=observed_at - timedelta(minutes=1),
        observed_at=observed_at,
        effective_from=effective_from,
        effective_until=effective_until,
        data_ref=f"external-data://{event_id}",
        authority_class=authority,
        confidence=0.95,
        object_relations=(
            TimelineObjectRelation(
                object_ref=f"context:{event_id}",
                object_kind=TimelineObjectKind.CONTEXT_SIGNAL,
                qualifier=TimelineObjectQualifier.CONTEXT,
            ),
        ),
        evidence_refs=(f"external-evidence://{event_id}",),
    )


def observation(
    *,
    event_id: str = "weather:rain",
    domain: ExternalContextDomain = ExternalContextDomain.WEATHER,
    claim_key: str = "severe_rain",
    claim_value=True,
    scope: GeographicScope | None = None,
    authority: TimelineAuthorityClass = TimelineAuthorityClass.VERIFIED_EXTERNAL,
    tenant_id: str = "tenant-a",
    observed_at: datetime = T1,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
):
    event = external_event(
        event_id=event_id,
        authority=authority,
        tenant_id=tenant_id,
        observed_at=observed_at,
        effective_from=effective_from,
        effective_until=effective_until,
    )
    return build_external_context_observation(
        event=event,
        observation_id=f"observation:{event_id}",
        domain=domain,
        claim_key=claim_key,
        claim_value=claim_value,
        geographic_scope=scope or locality_scope(),
    )


def material_orders_drop(previous, current):
    return build_company_metric_deviation(
        previous_world=previous,
        current_world=current,
        company_id="company-a",
        location_entity_id=LOCATION,
        metric_field_name="orders_per_hour",
        material_change_ratio=0.10,
    )


def test_verified_weather_plus_governed_orders_drop_requires_correlation_review_not_causality() -> None:
    previous = company_world(as_of=T0, orders_per_hour=100.0)
    current = company_world(as_of=T1, orders_per_hour=62.0)
    deviation = material_orders_drop(previous, current)

    receipt = assess_company_world_live_context(
        tenant_id="tenant-a",
        company_id="company-a",
        as_of=T1,
        current_world=current,
        location_binding=binding(current),
        observations=(observation(),),
        deviations=(deviation,),
    )

    assert deviation.direction is CompanyMetricDirection.DECREASE
    assert deviation.material is True
    assert receipt.disposition is ContextCompanyLinkDisposition.CORRELATED_REVIEW_REQUIRED
    assert receipt.company_operational_deviation_authorized is True
    assert receipt.context_coincident_with_company_deviation is True
    assert receipt.causal_claim_proven is False
    assert receipt.firm_company_causal_claim_authorized is False
    assert receipt.automatic_action_allowed is False
    assert receipt.execution_authority_granted is False
    assert "company_world_correlation_is_not_causality" in receipt.reason_codes


def test_verified_external_context_without_company_deviation_remains_context_only() -> None:
    current = company_world(as_of=T1, orders_per_hour=100.0)
    receipt = assess_company_world_live_context(
        tenant_id="tenant-a",
        company_id="company-a",
        as_of=T1,
        current_world=current,
        location_binding=binding(current),
        observations=(observation(),),
    )

    assert receipt.disposition is ContextCompanyLinkDisposition.CONTEXT_ONLY
    assert receipt.company_operational_deviation_authorized is False
    assert receipt.context_coincident_with_company_deviation is False
    assert receipt.causal_claim_proven is False


def test_wrong_locality_cannot_be_linked_to_company_location() -> None:
    current = company_world(as_of=T1, orders_per_hour=100.0)
    receipt = assess_company_world_live_context(
        tenant_id="tenant-a",
        company_id="company-a",
        as_of=T1,
        current_world=current,
        location_binding=binding(current),
        observations=(observation(scope=locality_scope("kadikoy")),),
    )

    assert receipt.disposition is ContextCompanyLinkDisposition.NO_APPLICABLE_CONTEXT
    state = receipt.observation_states[0]
    assert state.geography_match is False
    assert state.applicable is False
    assert state.blocker == "company_world_external_geography_mismatch"


def test_stale_traffic_observation_cannot_explain_current_company_state() -> None:
    current = company_world(as_of=T1, orders_per_hour=100.0)
    traffic = observation(
        event_id="traffic:stale",
        domain=ExternalContextDomain.TRAFFIC,
        claim_key="congestion",
        claim_value="severe",
        observed_at=T1 - timedelta(hours=2),
        effective_from=T1 - timedelta(hours=3),
        effective_until=T1 + timedelta(hours=1),
    )
    receipt = assess_company_world_live_context(
        tenant_id="tenant-a",
        company_id="company-a",
        as_of=T1,
        current_world=current,
        location_binding=binding(current),
        observations=(traffic,),
    )

    assert receipt.disposition is ContextCompanyLinkDisposition.NO_APPLICABLE_CONTEXT
    assert receipt.observation_states[0].fresh is False
    assert receipt.observation_states[0].blocker == "company_world_external_context_stale"


def test_context_only_authority_cannot_be_promoted_into_verified_company_context() -> None:
    current = company_world(as_of=T1, orders_per_hour=100.0)
    weak = observation(
        event_id="weather:weak",
        authority=TimelineAuthorityClass.CONTEXT_ONLY,
    )
    receipt = assess_company_world_live_context(
        tenant_id="tenant-a",
        company_id="company-a",
        as_of=T1,
        current_world=current,
        location_binding=binding(current),
        observations=(weak,),
    )

    assert receipt.disposition is ContextCompanyLinkDisposition.NO_APPLICABLE_CONTEXT
    assert receipt.observation_states[0].trusted_authority is False
    assert receipt.observation_states[0].blocker == "company_world_external_authority_insufficient"


def test_cross_tenant_and_future_external_context_fail_closed() -> None:
    current = company_world(as_of=T1, orders_per_hour=100.0)

    with pytest.raises(ValueError, match="cross_tenant_external_context"):
        assess_company_world_live_context(
            tenant_id="tenant-a",
            company_id="company-a",
            as_of=T1,
            current_world=current,
            location_binding=binding(current),
            observations=(observation(event_id="weather:other", tenant_id="tenant-b"),),
        )

    with pytest.raises(ValueError, match="external_context_from_future"):
        assess_company_world_live_context(
            tenant_id="tenant-a",
            company_id="company-a",
            as_of=T1,
            current_world=current,
            location_binding=binding(current),
            observations=(
                observation(
                    event_id="weather:future-read",
                    observed_at=T1 + timedelta(minutes=1),
                ),
            ),
        )


def test_equal_authority_external_conflict_forces_evidence_conflict() -> None:
    current = company_world(as_of=T1, orders_per_hour=100.0)
    rainy = observation(event_id="weather:a", claim_value=True)
    dry = observation(event_id="weather:b", claim_value=False)

    receipt = assess_company_world_live_context(
        tenant_id="tenant-a",
        company_id="company-a",
        as_of=T1,
        current_world=current,
        location_binding=binding(current),
        observations=(rainy, dry),
    )

    assert receipt.disposition is ContextCompanyLinkDisposition.EVIDENCE_CONFLICT
    assert receipt.causal_claim_proven is False
    assert receipt.automatic_action_allowed is False
    assert "company_world_external_context_conflict" in receipt.reason_codes


def test_upcoming_verified_public_event_is_relevant_inside_bounded_lookahead() -> None:
    current = company_world(as_of=T1, orders_per_hour=100.0)
    marathon = observation(
        event_id="event:marathon",
        domain=ExternalContextDomain.PUBLIC_EVENT,
        claim_key="road_closure_event",
        claim_value="marathon",
        observed_at=T1,
        effective_from=T1 + timedelta(hours=6),
        effective_until=T1 + timedelta(hours=10),
    )

    receipt = assess_company_world_live_context(
        tenant_id="tenant-a",
        company_id="company-a",
        as_of=T1,
        current_world=current,
        location_binding=binding(current),
        observations=(marathon,),
    )

    assert receipt.disposition is ContextCompanyLinkDisposition.CONTEXT_ONLY
    assert receipt.observation_states[0].temporally_relevant is True
    assert receipt.observation_states[0].applicable is True
    assert receipt.causal_claim_proven is False


def test_company_metric_contradiction_blocks_deviation_instead_of_guessing() -> None:
    previous = company_world(as_of=T0, orders_per_hour=100.0)
    current = company_world(
        as_of=T1,
        orders_per_hour=70.0,
        conflicting_value=45.0,
    )

    with pytest.raises(ValueError, match="metric_field_contradicted"):
        material_orders_drop(previous, current)


def test_location_binding_requires_company_owned_truth_and_exact_world_lineage() -> None:
    previous = company_world(as_of=T0, orders_per_hour=100.0)
    current = company_world(as_of=T1, orders_per_hour=90.0)

    with pytest.raises(ValueError, match="location_binding_requires_company_truth"):
        build_company_location_binding(
            world=current,
            company_id="company-a",
            location_entity_id=LOCATION,
            scope=fulya_scope(),
            truth_class=TruthClass.VERIFIED_EXTERNAL,
            observed_at=current.as_of,
            evidence_ref="external-evidence://location/guess",
        )

    stale_binding = binding(previous)
    with pytest.raises(ValueError, match="location_binding_world_stale"):
        assess_company_world_live_context(
            tenant_id="tenant-a",
            company_id="company-a",
            as_of=T1,
            current_world=current,
            location_binding=stale_binding,
        )


def test_external_company_assertion_event_cannot_enter_external_context_bridge() -> None:
    event = build_timeline_event(
        event_id="company:orders",
        event_type="eay.ops.orders.changed",
        event_kind=TimelineEventKind.COMPANY_ASSERTION,
        source_ref="company://orders",
        tenant_id="tenant-a",
        occurred_at=T1 - timedelta(minutes=1),
        observed_at=T1,
        data_ref="company-data://orders",
        authority_class=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        confidence=0.99,
        object_relations=(
            TimelineObjectRelation(
                object_ref=LOCATION,
                object_kind=TimelineObjectKind.WORLD_ENTITY,
                qualifier=TimelineObjectQualifier.SUBJECT,
            ),
        ),
        evidence_refs=("company-evidence://orders",),
    )

    with pytest.raises(ValueError, match="requires_context_event"):
        build_external_context_observation(
            event=event,
            observation_id="observation:company-orders",
            domain=ExternalContextDomain.WEATHER,
            claim_key="not-weather",
            claim_value=True,
            geographic_scope=locality_scope(),
        )
