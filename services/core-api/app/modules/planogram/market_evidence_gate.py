"""Market-leadership evidence veto for Planogram previews."""

from __future__ import annotations

from typing import Any

EVIDENCE_GATE_VERSION = "planogram-market-evidence-gate-v1"


def evaluate_market_evidence_gate(
    *,
    convergence: dict[str, Any] | None,
    shadow_backtest: dict[str, Any] | None,
    blind_benchmark: dict[str, Any] | None = None,
    realogram: dict[str, Any] | None = None,
    shelf_scan: dict[str, Any] | None = None,
    external_authority: dict[str, bool] | None = None,
) -> dict[str, Any]:
    convergence = convergence or {}
    shadow_backtest = shadow_backtest or {}
    blind_benchmark = blind_benchmark or {}
    realogram = realogram or {}
    shelf_scan = shelf_scan or {}
    external_authority = external_authority or {}

    repository_gates = {
        "commercial_physical_converged": bool(convergence.get("repository_converged")),
        "shadow_backtest_available": bool(shadow_backtest.get("available")),
        "shadow_backtest_evidence_complete": bool(shadow_backtest.get("evidence_complete")),
        "shadow_backtest_minimum_pairs": bool(shadow_backtest.get("minimum_pair_gate_passed")),
        "blind_benchmark_available": bool(blind_benchmark.get("available")),
        "blind_benchmark_is_blind": blind_benchmark.get("blind") is True,
        "realogram_available": bool(realogram.get("available")),
        "realogram_provenance_fields_complete": bool(
            realogram.get("provenance_fields_complete")
        ),
        "shelf_scan_review_candidate": bool(
            shelf_scan.get("candidate_ready_for_human_review")
        ),
    }
    external_gates = {
        "server_connector_provenance_verified": external_authority.get(
            "server_connector_provenance_verified"
        )
        is True,
        "independent_expert_reveal_verified": external_authority.get(
            "independent_expert_reveal_verified"
        )
        is True,
        "controlled_store_pilot_verified": external_authority.get(
            "controlled_store_pilot_verified"
        )
        is True,
        "field_installation_acceptance_verified": external_authority.get(
            "field_installation_acceptance_verified"
        )
        is True,
    }
    repository_ready = all(repository_gates.values())
    external_ready = all(external_gates.values())
    blockers = [name for name, passed in repository_gates.items() if not passed]
    blockers.extend(name for name, passed in external_gates.items() if not passed)
    return {
        "gate_version": EVIDENCE_GATE_VERSION,
        "repository_gates": repository_gates,
        "external_gates": external_gates,
        "repository_ready_for_independent_review": repository_ready,
        "external_field_evidence_complete": external_ready,
        "blockers": blockers,
        "production_promotion_allowed": repository_ready and external_ready,
        "market_leadership_claim_allowed": repository_ready and external_ready,
        "preview_request_can_grant_external_authority": False,
        "evidence_boundary": (
            "repository capability and synthetic/backtest evidence cannot grant a market "
            "leadership claim without independently verified field provenance and acceptance"
        ),
    }
