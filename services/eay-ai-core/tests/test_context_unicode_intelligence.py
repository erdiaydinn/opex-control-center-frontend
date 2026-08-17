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


def test_istanbul_and_kadikoy_unicode_variants_match_same_location():
    signal = ContextSignal(
        signal_id="event",
        kind=ContextKind.CITY_EVENT,
        title="Local event",
        starts_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        observed_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
        locations=("İstanbul Kadıköy",),
        expected_impacts=(ImpactDimension.ORDER_VOLUME,),
        source_name="official",
        source_url="https://example.gov.tr/event",
        source_class=ContextSourceClass.OFFICIAL,
        source_confidence=0.95,
    )
    observation = OperationalObservation(
        observation_id="orders",
        metric_name="orders",
        impact_dimension=ImpactDimension.ORDER_VOLUME,
        value=70,
        baseline_value=100,
        unit="count",
        starts_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        locations=("Istanbul Kadikoy",),
        provenance_ref="ops://orders",
    )

    relation = assess_relation(signal, observation)

    assert relation.geographic_overlap == 1.0
    assert relation.status is RelationStatus.PLAUSIBLE_CONTRIBUTOR
