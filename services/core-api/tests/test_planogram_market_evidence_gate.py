from app.modules.planogram.market_evidence_gate import evaluate_market_evidence_gate


def _repository_evidence():
    return dict(
        convergence={
            "repository_converged": True,
            "physical_capacity_v2": {"valid": True},
        },
        shadow_backtest={
            "available": True,
            "evidence_complete": True,
            "minimum_pair_gate_passed": True,
        },
        blind_benchmark={"available": True, "blind": True},
        realogram={
            "available": True,
            "provenance_fields_complete": True,
            "action_state_contract": "stable-id-dedup-open-resolved-v1",
        },
        shelf_scan={"candidate_ready_for_human_review": True},
    )


def _external_authority():
    return {
        "authority_source": "server_verified_evidence_registry_v1",
        "evidence_bundle_id": "bundle-1",
        "evidence_bundle_hash": "a" * 64,
        "verified_at": "2026-08-20T17:00:00Z",
        "verifier_subject": "evidence-registry",
        "server_connector_provenance_verified": True,
        "independent_expert_reveal_verified": True,
        "controlled_store_pilot_verified": True,
        "field_installation_acceptance_verified": True,
    }


def test_repository_success_cannot_grant_market_claim_without_external_authority():
    result = evaluate_market_evidence_gate(**_repository_evidence())
    assert result["repository_ready_for_independent_review"] is True
    assert result["external_field_evidence_complete"] is False
    assert result["market_leadership_claim_allowed"] is False


def test_preview_context_hard_denies_even_complete_external_authority():
    result = evaluate_market_evidence_gate(
        **_repository_evidence(),
        external_authority=_external_authority(),
    )
    assert result["external_field_evidence_complete"] is True
    assert result["production_promotion_allowed"] is False
    assert result["market_leadership_claim_allowed"] is False
    assert "preview_context_cannot_promote_or_claim" in result["blockers"]


def test_non_preview_requires_server_registry_attestation():
    authority = _external_authority()
    authority.pop("evidence_bundle_hash")
    result = evaluate_market_evidence_gate(
        **_repository_evidence(),
        external_authority=authority,
        preview_context=False,
    )
    assert result["server_evidence_registry_attested"] is False
    assert result["market_leadership_claim_allowed"] is False


def test_non_preview_can_promote_only_after_all_attested_gates():
    result = evaluate_market_evidence_gate(
        **_repository_evidence(),
        external_authority=_external_authority(),
        preview_context=False,
    )
    assert result["production_promotion_allowed"] is True
    assert result["market_leadership_claim_allowed"] is True
