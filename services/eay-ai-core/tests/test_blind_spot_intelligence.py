from app.blind_spot_intelligence import (
    BlindSpotInput,
    BlindSpotStatus,
    assess_blind_spot,
)
from app.hypothesis_intelligence import (
    EvidenceDirection,
    HypothesisCandidate,
    HypothesisEvidence,
    rank_hypotheses,
)


def test_material_anomaly_without_hypotheses_becomes_explicit_blind_spot():
    result = assess_blind_spot(
        BlindSpotInput(
            anomaly_id="orders-drop",
            metric_name="orders",
            deviation_pct=-24.0,
            evidence_domains_available=("availability_inventory",),
        )
    )

    assert result.status is BlindSpotStatus.UNEXPLAINED_MATERIAL_ANOMALY
    assert result.investigation_required is True
    assert "weather" in result.missing_evidence_domains
    assert "do_not_invent_root_cause" in result.warnings


def test_small_noise_does_not_trigger_unknown_unknown_investigation():
    result = assess_blind_spot(
        BlindSpotInput(
            anomaly_id="small-change",
            metric_name="orders",
            deviation_pct=-3.0,
        )
    )

    assert result.status is BlindSpotStatus.EXPLAINED_ENOUGH
    assert result.material is False
    assert result.investigation_required is False


def test_partial_hypothesis_still_requests_missing_evidence():
    ranking = rank_hypotheses(
        [
            HypothesisCandidate(
                hypothesis_id="weather",
                label="Weather contributed",
                evidence=(
                    HypothesisEvidence(
                        evidence_ref="weather://rain",
                        direction=EvidenceDirection.SUPPORT,
                        weight=0.8,
                        source_quality=0.8,
                        independent_source_key="weather",
                    ),
                    HypothesisEvidence(
                        evidence_ref="ops://orders",
                        direction=EvidenceDirection.SUPPORT,
                        weight=0.7,
                        source_quality=0.9,
                        independent_source_key="orders",
                    ),
                ),
            )
        ]
    )
    result = assess_blind_spot(
        BlindSpotInput(
            anomaly_id="orders-drop",
            metric_name="orders",
            deviation_pct=-22.0,
            evidence_domains_available=("weather", "demand_calendar"),
            hypothesis_ranking=ranking,
        )
    )

    assert result.status in {
        BlindSpotStatus.PARTIALLY_EXPLAINED,
        BlindSpotStatus.UNEXPLAINED_MATERIAL_ANOMALY,
    }
    assert result.investigation_required is True
