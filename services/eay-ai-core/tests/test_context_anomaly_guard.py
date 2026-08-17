from datetime import datetime, timezone

from app.context_intelligence import (
    ContextKind,
    ContextSignal,
    ContextSourceClass,
    ImpactDimension,
    OperationalObservation,
    RelationStatus,
    assess_relation,
)

UTC = timezone.utc


def _dt(hour: int) -> datetime:
    return datetime(2026, 11, 1, hour, 0, tzinfo=UTC)


def _signal() -> ContextSignal:
    return ContextSignal(
        signal_id="istanbul-marathon-2026",
        kind=ContextKind.CITY_EVENT,
        title="Istanbul marathon and associated road closures",
        starts_at=_dt(6),
        ends_at=_dt(16),
        observed_at=_dt(5),
        locations=("Istanbul",),
        expected_impacts=(ImpactDimension.ORDER_VOLUME,),
        source_name="official-city-event-feed",
        source_url="https://example.istanbul/events/marathon",
        source_class=ContextSourceClass.OFFICIAL,
        source_confidence=0.96,
    )


def _orders(*, value: float, baseline: float | None) -> OperationalObservation:
    return OperationalObservation(
        observation_id="orders-istanbul-0800-1400",
        metric_name="orders",
        impact_dimension=ImpactDimension.ORDER_VOLUME,
        value=value,
        baseline_value=baseline,
        unit="count",
        starts_at=_dt(8),
        ends_at=_dt(14),
        locations=("Istanbul",),
        provenance_ref="ops://orders/governed/istanbul/2026-11-01",
    )


def test_matching_event_is_not_attributed_when_operation_is_within_normal_band():
    relation = assess_relation(_signal(), _orders(value=9900, baseline=10000))

    assert relation.status is RelationStatus.INSUFFICIENT
    assert relation.deviation_pct == -1.0
    assert "operational_anomaly_not_material" in relation.blockers


def test_missing_baseline_can_only_produce_context_candidate():
    relation = assess_relation(_signal(), _orders(value=7100, baseline=None))

    assert relation.status is RelationStatus.CONTEXT_CANDIDATE
    assert relation.deviation_pct is None
    assert relation.anomaly_strength == 0.0
    assert "baseline_evidence_missing" in relation.warnings
