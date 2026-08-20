from app.modules.planogram.market_evidence_gate import evaluate_market_evidence_gate


def _repository_evidence():
    return dict(
        convergence={"repository_converged": True},
        shadow_backtest={
            "available": True,
            "evidence_complete": True,
            "minimum_pair_gate_passed": True,
        },
        blind_benchmark={"available": True, "blind": True},
        realogram={"available": True, "provenance_fields_complete": True},
        shelf_scan={"candidate_ready_for_human_review": True},
    )


def test_repository_success_cannot_grant_market_claim_without_external_authority():
    result = evaluate_market_evidence_gate(**_repository_evidence())
    assert result["repository_ready_for_independent_review"] is True
    assert result["external_field_evidence_complete"] is False
    assert result["market_leadership_claim_allowed"] is False


def test_external_authority_must_be_complete_for_claim():
    result = evaluate_market_evidence_gate(
        **_repository_evidence(),
        external_authority={
            "server_connector_provenance_verified": True,
            "independent_expert_reveal_verified": True,
            "controlled_store_pilot_verified": True,
            "field_installation_acceptance_verified": True,
        },
    )
    assert result["market_leadership_claim_allowed"] is True
    assert result["preview_request_can_grant_external_authority"] is False
