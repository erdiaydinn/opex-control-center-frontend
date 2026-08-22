from datetime import datetime, timezone

import pytest

from app.context_intelligence import (
    ContextKind,
    ContextSignal,
    ContextSourceClass,
    ImpactDimension,
    OperationalObservation,
    RelationStatus,
    assess_relation,
    build_context_insight,
)

UTC = timezone.utc


def _dt(hour: int) -> datetime:
    return datetime(2026, 11, 1, hour, 0, tzinfo=UTC)


def _marathon_signal() -> ContextSignal:
    return ContextSignal(
        signal_id="istanbul-marathon-2026",
        kind=ContextKind.CITY_EVENT,
        title="Istanbul marathon and associated road closures",
        starts_at=_dt(6),
        ends_at=_dt(16),
        observed_at=_dt(5),
        locations=("Istanbul",),
        expected_impacts=(
            ImpactDimension.ORDER_VOLUME,
            ImpactDimension.STORE_ACCESS,
            ImpactDimension.DELIVERY_SPEED,
            ImpactDimension.CLOSURE_TIME,
        ),
        source_name="official-city-event-feed",
        source_url="https://example.istanbul/events/marathon",
        source_class=ContextSourceClass.OFFICIAL,
        source_confidence=0.96,
    )


def _orders() -> OperationalObservation:
    return OperationalObservation(
        observation_id="orders-istanbul-0800-1400",
        metric_name="orders",
        impact_dimension=ImpactDimension.ORDER_VOLUME,
        value=7100,
        baseline_value=10000,
        unit="count",
        starts_at=_dt(8),
        ends_at=_dt(14),
        locations=("Istanbul",),
        provenance_ref="ops://orders/governed/istanbul/2026-11-01",
    )


def _closure_time() -> OperationalObservation:
    return OperationalObservation(
        observation_id="closure-istanbul-0800-1400",
        metric_name="store_closure_minutes",
        impact_dimension=ImpactDimension.CLOSURE_TIME,
        value=96,
        baseline_value=31,
        unit="minutes",
        starts_at=_dt(8),
        ends_at=_dt(14),
        locations=("Istanbul",),
        provenance_ref="ops://store-closure/governed/istanbul/2026-11-01",
    )


def test_marathon_can_be_plausible_contributor_without_becoming_causal_truth():
    insight = build_context_insight(_marathon_signal(), [_orders(), _closure_time()])

    assert insight.status is RelationStatus.PLAUSIBLE_CONTRIBUTOR
    assert insight.confidence >= 0.65
    assert insight.causality_proven is False
    assert all(item.causality_proven is False for item in insight.relations)
    assert {item.observation_id for item in insight.relations} == {
        "orders-istanbul-0800-1400",
        "closure-istanbul-0800-1400",
    }
    assert "correlation_is_not_causation" in insight.warnings
    assert "external_context_never_overrides_governed_operational_truth" in insight.warnings


def test_weather_signal_in_different_city_fails_geographic_overlap():
    rain = ContextSignal(
        signal_id="ankara-rain",
        kind=ContextKind.WEATHER,
        title="Heavy rain",
        starts_at=_dt(8),
        ends_at=_dt(14),
        observed_at=_dt(7),
        locations=("Ankara",),
        expected_impacts=(ImpactDimension.ORDER_VOLUME,),
        source_name="weather-provider",
        source_url="https://weather.example/ankara",
        source_class=ContextSourceClass.VERIFIED_PROVIDER,
        source_confidence=0.90,
    )

    relation = assess_relation(rain, _orders())

    assert relation.status is RelationStatus.INSUFFICIENT
    assert relation.geographic_overlap == 0.0
    assert "no_geographic_overlap" in relation.blockers


def test_non_overlapping_time_window_cannot_explain_operational_anomaly():
    event = _marathon_signal().model_copy(
        update={"starts_at": _dt(17), "ends_at": _dt(20)}
    )

    relation = assess_relation(event, _orders())

    assert relation.status is RelationStatus.INSUFFICIENT
    assert relation.temporal_overlap == 0.0
    assert "no_temporal_overlap" in relation.blockers


def test_semantically_unrelated_context_is_rejected():
    regulatory = ContextSignal(
        signal_id="regulatory-signal",
        kind=ContextKind.REGULATORY_SIGNAL,
        title="New employment compliance publication detected",
        starts_at=_dt(8),
        ends_at=_dt(14),
        observed_at=_dt(8),
        locations=("global",),
        expected_impacts=(ImpactDimension.COMPLIANCE, ImpactDimension.LABOR),
        source_name="official-regulatory-feed",
        source_url="https://www.resmigazete.gov.tr/example",
        source_class=ContextSourceClass.OFFICIAL,
        source_confidence=0.99,
    )

    relation = assess_relation(regulatory, _orders())

    assert relation.status is RelationStatus.INSUFFICIENT
    assert relation.semantic_overlap == 0.0
    assert "impact_dimension_mismatch" in relation.blockers


def test_external_signal_cannot_self_promote_into_binding_legal_authority():
    with pytest.raises(ValueError, match="context_signal_cannot_be_binding_authority"):
        _marathon_signal().model_copy(update={"binding_legal_evidence": True}).model_validate(
            _marathon_signal().model_dump() | {"binding_legal_evidence": True}
        )


def test_ungoverned_internal_metric_is_rejected():
    with pytest.raises(ValueError, match="governed_operational_truth_required"):
        OperationalObservation(
            observation_id="browser-authored-orders",
            metric_name="orders",
            impact_dimension=ImpactDimension.ORDER_VOLUME,
            value=1,
            unit="count",
            starts_at=_dt(8),
            ends_at=_dt(9),
            locations=("Istanbul",),
            provenance_ref="client://browser",
            governed_operational_truth=False,
        )


def test_context_source_requires_https_and_timezone_aware_evidence():
    with pytest.raises(ValueError, match="context_source_https_required"):
        _marathon_signal().model_copy(update={"source_url": "http://example.com/event"}).model_validate(
            _marathon_signal().model_dump() | {"source_url": "http://example.com/event"}
        )

    payload = _marathon_signal().model_dump()
    payload["starts_at"] = datetime(2026, 11, 1, 6, 0)
    with pytest.raises(ValueError, match="context_signal_timezone_required"):
        ContextSignal.model_validate(payload)


def test_observation_exposes_deterministic_baseline_deviation():
    assert _orders().deviation_pct == -29.0
    assert _closure_time().deviation_pct == pytest.approx(209.6774)
