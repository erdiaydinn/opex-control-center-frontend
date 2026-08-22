from app.council_runtime import (
    ClaimStance,
    CritiqueSeverity,
    EngineClaim,
    EngineCritique,
    EngineProposal,
    synthesize_council,
)


def _proposal(proposal_id, provider, confidence=0.9, action="action://prepare-capacity"):
    return EngineProposal(
        proposal_id=proposal_id,
        engine_id=f"engine:{proposal_id}",
        provider_key=provider,
        answer_ref=f"answer://{proposal_id}",
        claims=(
            EngineClaim(
                claim_key="capacity-risk",
                statement="Capacity risk is material in the peak window",
                confidence=confidence,
                evidence_refs=(f"evidence://{proposal_id}",),
            ),
        ),
        proposed_action_refs=(action,),
    )


def test_two_independent_providers_can_accept_claim_and_shared_action():
    synthesis = synthesize_council(
        proposals=[_proposal("a", "provider-a"), _proposal("b", "provider-b")],
        critiques=[],
    )

    result = synthesis.claim_results[0]
    assert result.accepted is True
    assert result.independent_supporters == 2
    assert synthesis.accepted_action_refs == ("action://prepare-capacity",)
    assert synthesis.decision_ready is True
    assert synthesis.execution_allowed is False


def test_multiple_samples_from_same_provider_do_not_fake_diversity():
    synthesis = synthesize_council(
        proposals=[_proposal("a", "provider-a"), _proposal("b", "provider-a")],
        critiques=[],
    )

    assert synthesis.claim_results[0].accepted is False
    assert synthesis.provider_diversity == 1
    assert "council_provider_diversity_insufficient" in synthesis.blockers


def test_critical_independent_refutation_blocks_claim():
    synthesis = synthesize_council(
        proposals=[_proposal("a", "provider-a"), _proposal("b", "provider-b")],
        critiques=[
            EngineCritique(
                critique_id="critique-1",
                critic_engine_id="critic-c",
                critic_provider_key="provider-c",
                target_claim_key="capacity-risk",
                stance=ClaimStance.REFUTE,
                severity=CritiqueSeverity.CRITICAL,
                reasoning_ref="critique://reason",
                evidence_refs=("evidence://counter",),
            )
        ],
    )

    result = synthesis.claim_results[0]
    assert result.accepted is False
    assert result.contested is True
    assert result.independent_refuters == 1
    assert "council_critical_refutation_present" in result.blockers
    assert synthesis.decision_ready is False


def test_disagreement_is_preserved_in_evidence_and_confidence():
    synthesis = synthesize_council(
        proposals=[_proposal("a", "provider-a", 0.95), _proposal("b", "provider-b", 0.90)],
        critiques=[
            EngineCritique(
                critique_id="critique-material",
                critic_engine_id="critic-c",
                critic_provider_key="provider-c",
                target_claim_key="capacity-risk",
                stance=ClaimStance.REFUTE,
                severity=CritiqueSeverity.MATERIAL,
                reasoning_ref="critique://material",
                evidence_refs=("evidence://material-counter",),
            )
        ],
    )

    result = synthesis.claim_results[0]
    assert result.contested is True
    assert result.weighted_confidence < 0.95
    assert "evidence://material-counter" in result.evidence_refs
    assert result.accepted is False
