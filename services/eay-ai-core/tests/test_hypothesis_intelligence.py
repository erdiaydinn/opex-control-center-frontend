from app.hypothesis_intelligence import (
    EvidenceDirection,
    HypothesisCandidate,
    HypothesisEvidence,
    rank_hypotheses,
)


def _evidence(ref: str, direction: EvidenceDirection, weight: float, source: str):
    return HypothesisEvidence(
        evidence_ref=ref,
        direction=direction,
        weight=weight,
        source_quality=0.95,
        independent_source_key=source,
    )


def test_event_hypothesis_can_lead_without_becoming_causal_proof():
    marathon = HypothesisCandidate(
        hypothesis_id="marathon",
        label="Marathon and road closures contributed to the order drop",
        evidence=(
            _evidence("ctx://marathon", EvidenceDirection.SUPPORT, 0.95, "city-event"),
            _evidence("ops://orders", EvidenceDirection.SUPPORT, 0.90, "orders"),
            _evidence("cf://matched-controls", EvidenceDirection.SUPPORT, 0.90, "controls"),
            _evidence("ops://availability-normal", EvidenceDirection.REFUTE, 0.20, "availability"),
        ),
    )
    staffing = HypothesisCandidate(
        hypothesis_id="staffing",
        label="Staffing shortage explains the drop",
        evidence=(
            _evidence("ops://roster", EvidenceDirection.SUPPORT, 0.30, "roster"),
            _evidence("ops://attendance", EvidenceDirection.REFUTE, 0.60, "attendance"),
            _evidence("ops://productivity", EvidenceDirection.REFUTE, 0.50, "productivity"),
        ),
    )

    ranking = rank_hypotheses([marathon, staffing])

    assert ranking.leading_hypothesis_id == "marathon"
    assert ranking.assessments[0].causal_proof is False
    assert ranking.leading_margin is not None


def test_one_sided_explanation_is_never_decisive_without_counterevidence():
    candidate = HypothesisCandidate(
        hypothesis_id="rain",
        label="Rain caused the demand increase",
        evidence=(
            _evidence("weather://rain", EvidenceDirection.SUPPORT, 1.0, "weather"),
            _evidence("ops://orders", EvidenceDirection.SUPPORT, 1.0, "orders"),
            _evidence("ops://riders", EvidenceDirection.SUPPORT, 0.8, "riders"),
        ),
    )

    ranking = rank_hypotheses([candidate])

    assert ranking.decisive is False
    assert ranking.requires_more_evidence is True
    assert "counterevidence_missing" in ranking.blockers


def test_close_competing_explanations_force_more_evidence():
    event = HypothesisCandidate(
        hypothesis_id="event",
        label="City event",
        evidence=(
            _evidence("ctx://event", EvidenceDirection.SUPPORT, 0.85, "event"),
            _evidence("ops://orders", EvidenceDirection.SUPPORT, 0.75, "orders"),
            _evidence("ops://counter", EvidenceDirection.REFUTE, 0.20, "counter"),
        ),
    )
    availability = HypothesisCandidate(
        hypothesis_id="availability",
        label="Availability deterioration",
        evidence=(
            _evidence("ops://availability", EvidenceDirection.SUPPORT, 0.82, "availability"),
            _evidence("ops://nsfr", EvidenceDirection.SUPPORT, 0.72, "nsfr"),
            _evidence("ops://control", EvidenceDirection.REFUTE, 0.18, "control"),
        ),
    )

    ranking = rank_hypotheses([event, availability])

    assert ranking.requires_more_evidence is True
    assert "competing_hypotheses_too_close" in ranking.blockers


def test_pending_falsification_test_blocks_decisive_output():
    candidate = HypothesisCandidate(
        hypothesis_id="promotion",
        label="Promotion changed demand",
        evidence=(
            _evidence("commercial://campaign", EvidenceDirection.SUPPORT, 0.95, "campaign"),
            _evidence("ops://orders", EvidenceDirection.SUPPORT, 0.90, "orders"),
            _evidence("ops://control", EvidenceDirection.REFUTE, 0.10, "control"),
        ),
        missing_tests=("compare_non_promoted_matched_stores",),
    )

    ranking = rank_hypotheses([candidate])

    assert ranking.decisive is False
    assert "falsification_tests_pending" in ranking.blockers
