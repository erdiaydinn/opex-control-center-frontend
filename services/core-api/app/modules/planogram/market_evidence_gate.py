"""Market-leadership evidence veto for Planogram previews."""
from __future__ import annotations

import re
from typing import Any

EVIDENCE_GATE_VERSION = "planogram-market-evidence-gate-v2-attested-authority"
SERVER_EVIDENCE_SOURCE = "server_verified_evidence_registry_v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _external_registry_attested(external: dict[str, Any]) -> bool:
    bundle_hash = _text(external.get("evidence_bundle_hash")).lower()
    return bool(
        external.get("authority_source") == SERVER_EVIDENCE_SOURCE
        and _text(external.get("evidence_bundle_id"))
        and SHA256_RE.fullmatch(bundle_hash)
        and _text(external.get("verified_at"))
        and _text(external.get("verifier_subject"))
    )


def evaluate_market_evidence_gate(
    *,
    convergence: dict[str, Any] | None,
    shadow_backtest: dict[str, Any] | None,
    blind_benchmark: dict[str, Any] | None = None,
    realogram: dict[str, Any] | None = None,
    shelf_scan: dict[str, Any] | None = None,
    external_authority: dict[str, Any] | None = None,
    preview_context: bool = True,
) -> dict[str, Any]:
    convergence = convergence or {}
    shadow_backtest = shadow_backtest or {}
    blind_benchmark = blind_benchmark or {}
    realogram = realogram or {}
    shelf_scan = shelf_scan or {}
    external_authority = external_authority or {}

    capacity_v2 = convergence.get("physical_capacity_v2") or {}
    repository_gates = {
        "commercial_physical_converged": bool(convergence.get("repository_converged")),
        "physical_capacity_v2_valid": capacity_v2.get("valid") is True,
        "shadow_backtest_available": bool(shadow_backtest.get("available")),
        "shadow_backtest_evidence_complete": bool(shadow_backtest.get("evidence_complete")),
        "shadow_backtest_minimum_pairs": bool(
            shadow_backtest.get("minimum_pair_gate_passed")
        ),
        "blind_benchmark_available": bool(blind_benchmark.get("available")),
        "blind_benchmark_is_blind": blind_benchmark.get("blind") is True,
        "realogram_available": bool(realogram.get("available")),
        "realogram_provenance_fields_complete": bool(
            realogram.get("provenance_fields_complete")
        ),
        "realogram_action_lifecycle_stable": (
            realogram.get("action_state_contract")
            == "stable-id-dedup-open-resolved-v1"
        ),
        "shelf_scan_review_candidate": bool(
            shelf_scan.get("candidate_ready_for_human_review")
        ),
    }

    registry_attested = _external_registry_attested(external_authority)
    external_gates = {
        "server_evidence_registry_attested": registry_attested,
        "server_connector_provenance_verified": (
            registry_attested
            and external_authority.get("server_connector_provenance_verified") is True
        ),
        "independent_expert_reveal_verified": (
            registry_attested
            and external_authority.get("independent_expert_reveal_verified") is True
        ),
        "controlled_store_pilot_verified": (
            registry_attested
            and external_authority.get("controlled_store_pilot_verified") is True
        ),
        "field_installation_acceptance_verified": (
            registry_attested
            and external_authority.get("field_installation_acceptance_verified") is True
        ),
    }

    repository_ready = all(repository_gates.values())
    external_ready = all(external_gates.values())
    blockers = [name for name, passed in repository_gates.items() if not passed]
    blockers.extend(name for name, passed in external_gates.items() if not passed)
    if preview_context:
        blockers.append("preview_context_cannot_promote_or_claim")

    release_candidate = repository_ready and external_ready
    promotion_allowed = release_candidate and not preview_context
    return {
        "gate_version": EVIDENCE_GATE_VERSION,
        "repository_gates": repository_gates,
        "external_gates": external_gates,
        "repository_ready_for_independent_review": repository_ready,
        "external_field_evidence_complete": external_ready,
        "server_evidence_registry_attested": registry_attested,
        "preview_context": bool(preview_context),
        "blockers": list(dict.fromkeys(blockers)),
        "promotion_candidate_after_all_evidence": release_candidate,
        "production_promotion_allowed": promotion_allowed,
        "market_leadership_claim_allowed": promotion_allowed,
        "preview_request_can_grant_external_authority": False,
        "evidence_boundary": (
            "repository capability and backtest evidence cannot grant market leadership; "
            "external proof must be server-registry attested and preview contexts are "
            "hard-denied from promotion even when every evidence gate is present"
        ),
    }
