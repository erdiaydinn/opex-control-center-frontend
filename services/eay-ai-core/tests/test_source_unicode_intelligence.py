from datetime import datetime, timezone

from app.context_intelligence import ContextKind, ContextSourceClass
from app.source_governance import SourceEvidence, SourceGovernanceStatus, evaluate_source_evidence

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _evidence(evidence_id: str, domain: str, value: str) -> SourceEvidence:
    return SourceEvidence(
        evidence_id=evidence_id,
        kind=ContextKind.NEWS_AGENDA,
        claim_key="event.location",
        claim_value=value,
        observed_at=NOW,
        fetched_at=NOW,
        source_name=domain,
        source_url=f"https://{domain}/event",
        source_class=ContextSourceClass.REPUTABLE_NEWS,
        source_confidence=0.90,
    )


def test_istanbul_unicode_variants_do_not_create_false_contradiction():
    report = evaluate_source_evidence(
        [
            _evidence("a", "news-a.example", "İstanbul Kadıköy"),
            _evidence("b", "news-b.example", "Istanbul Kadikoy"),
        ],
        now=NOW,
        kind=ContextKind.NEWS_AGENDA,
    )

    assert report.status is SourceGovernanceStatus.TRUSTED
    assert report.contradiction_keys == ()
