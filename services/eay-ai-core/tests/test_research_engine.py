from datetime import datetime, timedelta, timezone

from app.research_engine import (
    ResearchEvidence,
    ResearchQuestion,
    ResearchRisk,
    ResearchRole,
    ResearchVerdict,
    SourceTier,
    assess_research,
    plan_research,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 3, 0, tzinfo=UTC)


def _question(**overrides):
    payload = dict(
        question_id="istanbul-demand",
        question="Did the event materially impact order rate % in Istanbul?",
        risk=ResearchRisk.HIGH,
        domains=("operations", "city-events"),
        as_of=NOW,
        requires_current_information=True,
        enforce_as_of_information_boundary=True,
        minimum_independent_sources=2,
    )
    payload.update(overrides)
    return ResearchQuestion(**payload)


def _evidence(evidence_id, publisher, **overrides):
    payload = dict(
        evidence_id=evidence_id,
        claim_key="event-impact",
        claim_value="material",
        source_url=f"https://{publisher}.example/evidence",
        source_domain=f"{publisher}.example",
        source_tier=SourceTier.AUTHORITATIVE_SECONDARY,
        publisher_key=publisher,
        published_at=NOW - timedelta(hours=2),
        fetched_at=NOW - timedelta(minutes=10),
        supports_claim=True,
        contradicts_claim=False,
        evidence_ref=f"evidence://{evidence_id}",
    )
    payload.update(overrides)
    return ResearchEvidence(**payload)


def test_high_risk_research_plans_primary_contradiction_and_quantitative_checks():
    mission = plan_research(_question())
    roles = {task.role for task in mission.tasks}

    assert ResearchRole.PRIMARY_SOURCE in roles
    assert ResearchRole.CONTRADICTION in roles
    assert ResearchRole.QUANTITATIVE_CHECK in roles
    assert mission.primary_source_required is True
    assert mission.contradiction_search_required is True


def test_high_risk_claim_needs_primary_source_and_independent_quorum():
    assessment = assess_research(
        _question(),
        claim_key="event-impact",
        evidence=[_evidence("one", "publisher-a")],
    )

    assert assessment.verdict is ResearchVerdict.INSUFFICIENT
    assert "research_primary_source_missing" in assessment.blockers
    assert "research_independent_support_quorum_missing" in assessment.blockers


def test_primary_plus_independent_corroboration_can_support_claim():
    assessment = assess_research(
        _question(),
        claim_key="event-impact",
        evidence=[
            _evidence("official", "official", source_tier=SourceTier.PRIMARY),
            _evidence("secondary", "publisher-b"),
        ],
    )

    assert assessment.verdict is ResearchVerdict.SUPPORTED
    assert assessment.primary_source_present is True
    assert assessment.independent_support_count == 2
    assert assessment.blockers == ()


def test_material_contradiction_is_exposed_not_averaged_away():
    assessment = assess_research(
        _question(),
        claim_key="event-impact",
        evidence=[
            _evidence("official", "official", source_tier=SourceTier.PRIMARY),
            _evidence("support", "publisher-b"),
            _evidence(
                "contradict",
                "publisher-c",
                supports_claim=False,
                contradicts_claim=True,
                claim_value="not-material",
            ),
        ],
    )

    assert assessment.verdict is ResearchVerdict.CONTESTED
    assert assessment.confidence_cap <= 0.60
    assert "research_material_contradiction_unresolved" in assessment.blockers


def test_stale_only_current_evidence_fails_closed():
    stale = _evidence(
        "old",
        "official",
        source_tier=SourceTier.PRIMARY,
        fetched_at=NOW - timedelta(days=60),
    )
    stale2 = _evidence("old2", "publisher-b", fetched_at=NOW - timedelta(days=50))
    assessment = assess_research(
        _question(),
        claim_key="event-impact",
        evidence=[stale, stale2],
    )

    assert assessment.verdict is ResearchVerdict.INSUFFICIENT
    assert "research_evidence_stale_only" in assessment.blockers


def test_future_published_evidence_cannot_leak_backward_into_as_of_conclusion():
    assessment = assess_research(
        _question(),
        claim_key="event-impact",
        evidence=[
            _evidence(
                "future-official",
                "official",
                source_tier=SourceTier.PRIMARY,
                published_at=NOW + timedelta(days=2),
                fetched_at=NOW + timedelta(days=2),
            ),
            _evidence(
                "future-secondary",
                "publisher-b",
                published_at=NOW + timedelta(days=1),
                fetched_at=NOW + timedelta(days=1),
            ),
        ],
    )

    assert assessment.verdict is ResearchVerdict.INSUFFICIENT
    assert assessment.temporally_unavailable_evidence_count == 2
    assert assessment.evidence_refs == ()
    assert set(assessment.excluded_evidence_refs) == {
        "evidence://future-official",
        "evidence://future-secondary",
    }
    assert "research_evidence_not_available_as_of" in assessment.blockers
    assert "research_no_eligible_evidence" in assessment.blockers
