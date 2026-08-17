from datetime import datetime, timedelta, timezone

from app.context_intelligence import ContextKind, ContextSourceClass
from app.source_governance import (
    SourceEvidence,
    SourceGovernanceStatus,
    evaluate_source_evidence,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 0, 0, tzinfo=UTC)


def _evidence(
    evidence_id: str,
    *,
    kind: ContextKind,
    domain: str,
    claim_key: str,
    claim_value: str,
    source_class: ContextSourceClass,
    age_minutes: int = 10,
    confidence: float = 0.9,
) -> SourceEvidence:
    fetched_at = NOW - timedelta(minutes=age_minutes)
    return SourceEvidence(
        evidence_id=evidence_id,
        kind=kind,
        claim_key=claim_key,
        claim_value=claim_value,
        observed_at=fetched_at - timedelta(minutes=1),
        fetched_at=fetched_at,
        source_name=domain,
        source_url=f"https://{domain}/evidence/{evidence_id}",
        source_class=source_class,
        source_confidence=confidence,
    )


def test_weather_can_be_trusted_from_one_fresh_verified_provider():
    report = evaluate_source_evidence(
        [
            _evidence(
                "rain-1",
                kind=ContextKind.WEATHER,
                domain="weather.example",
                claim_key="istanbul.rain.level",
                claim_value="heavy",
                source_class=ContextSourceClass.VERIFIED_PROVIDER,
            )
        ],
        now=NOW,
        kind=ContextKind.WEATHER,
    )

    assert report.status is SourceGovernanceStatus.TRUSTED
    assert report.independent_source_count == 1
    assert report.blockers == ()


def test_news_agenda_requires_independent_source_quorum():
    report = evaluate_source_evidence(
        [
            _evidence(
                "news-1",
                kind=ContextKind.NEWS_AGENDA,
                domain="news-a.example",
                claim_key="event.status",
                claim_value="confirmed",
                source_class=ContextSourceClass.REPUTABLE_NEWS,
            )
        ],
        now=NOW,
        kind=ContextKind.NEWS_AGENDA,
    )

    assert report.status is SourceGovernanceStatus.BLOCKED
    assert "independent_source_quorum_missing" in report.blockers


def test_two_independent_agenda_sources_satisfy_quorum():
    report = evaluate_source_evidence(
        [
            _evidence(
                "news-1",
                kind=ContextKind.NEWS_AGENDA,
                domain="news-a.example",
                claim_key="event.status",
                claim_value="confirmed",
                source_class=ContextSourceClass.REPUTABLE_NEWS,
            ),
            _evidence(
                "news-2",
                kind=ContextKind.NEWS_AGENDA,
                domain="news-b.example",
                claim_key="event.status",
                claim_value="confirmed",
                source_class=ContextSourceClass.REPUTABLE_NEWS,
            ),
        ],
        now=NOW,
        kind=ContextKind.NEWS_AGENDA,
    )

    assert report.status is SourceGovernanceStatus.TRUSTED
    assert report.independent_source_count == 2


def test_macro_economic_claim_requires_official_source():
    report = evaluate_source_evidence(
        [
            _evidence(
                "macro-news",
                kind=ContextKind.MACRO_ECONOMIC,
                domain="economy-news.example",
                claim_key="policy_rate",
                claim_value="43",
                source_class=ContextSourceClass.REPUTABLE_NEWS,
            )
        ],
        now=NOW,
        kind=ContextKind.MACRO_ECONOMIC,
    )

    assert report.status is SourceGovernanceStatus.BLOCKED
    assert "official_source_required" in report.blockers


def test_stale_weather_is_blocked_even_if_provider_is_verified():
    report = evaluate_source_evidence(
        [
            _evidence(
                "rain-old",
                kind=ContextKind.WEATHER,
                domain="weather.example",
                claim_key="istanbul.rain.level",
                claim_value="heavy",
                source_class=ContextSourceClass.VERIFIED_PROVIDER,
                age_minutes=121,
            )
        ],
        now=NOW,
        kind=ContextKind.WEATHER,
    )

    assert report.status is SourceGovernanceStatus.BLOCKED
    assert report.usable_evidence_ids == ()
    assert report.stale_evidence_ids == ("rain-old",)
    assert "fresh_source_evidence_missing" in report.blockers


def test_conflicting_fresh_sources_degrade_confidence_without_inventing_consensus():
    report = evaluate_source_evidence(
        [
            _evidence(
                "event-a",
                kind=ContextKind.CITY_EVENT,
                domain="city.example",
                claim_key="road.closed",
                claim_value="yes",
                source_class=ContextSourceClass.OFFICIAL,
                confidence=0.98,
            ),
            _evidence(
                "event-b",
                kind=ContextKind.CITY_EVENT,
                domain="traffic.example",
                claim_key="road.closed",
                claim_value="no",
                source_class=ContextSourceClass.VERIFIED_PROVIDER,
                confidence=0.91,
            ),
        ],
        now=NOW,
        kind=ContextKind.CITY_EVENT,
    )

    assert report.status is SourceGovernanceStatus.DEGRADED
    assert report.contradiction_keys == ("road.closed",)
    assert report.confidence_cap <= 0.55
    assert "source_claim_contradiction_detected" in report.warnings
