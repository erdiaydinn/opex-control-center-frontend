"""Evidence-bound economics for one fingerprint-replayed V5 scenario."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import physical_economics
from physical_layout_candidate_preview import preview_physical_layout_candidate

CANDIDATE_ECONOMICS_VERSION = "physical-layout-candidate-economics-v1"


def evaluate_physical_layout_candidate_economics(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    layout_fingerprint: str,
    assumptions: dict[str, Any],
    mode: str = "HYBRID",
    max_layout_candidates: int = 16,
    max_allocation_candidates: int = 12,
    require_images: bool = True,
) -> dict[str, Any]:
    replay = preview_physical_layout_candidate(
        products=deepcopy(products),
        layout=deepcopy(layout),
        store_dna=deepcopy(store_dna),
        orders=deepcopy(orders),
        layout_fingerprint=layout_fingerprint,
        mode=mode,
        max_layout_candidates=max_layout_candidates,
        max_allocation_candidates=max_allocation_candidates,
        require_images=require_images,
    )
    if not replay.get("available"):
        return {
            "candidate_economics_version": CANDIDATE_ECONOMICS_VERSION,
            "available": False,
            "reason": "candidate_replay_unavailable",
            "replay_reason": replay.get("reason"),
            "production_evidence": False,
            "finance_approved": False,
            "investment_decision_allowed": False,
            "realized_savings_proven": False,
        }

    baseline = replay.get("baseline_candidate_summary")
    candidate = replay.get("candidate_summary")
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return {
            "candidate_economics_version": CANDIDATE_ECONOMICS_VERSION,
            "available": False,
            "reason": "baseline_or_candidate_summary_missing",
            "production_evidence": False,
            "finance_approved": False,
            "investment_decision_allowed": False,
            "realized_savings_proven": False,
        }

    candidate_label = str(candidate.get("label") or "").strip()
    economics_input = {
        "physical_layout_optimizer": {
            "allowed": True,
            "selected_layout_label": candidate_label,
            "candidates": [deepcopy(baseline), deepcopy(candidate)],
        }
    }
    economics = physical_economics.evaluate_physical_layout_economics(
        physical_layout_result=economics_input,
        assumptions=deepcopy(assumptions),
    )
    if not isinstance(economics, dict):
        return {
            "candidate_economics_version": CANDIDATE_ECONOMICS_VERSION,
            "available": False,
            "reason": "economics_result_invalid",
            "production_evidence": False,
            "finance_approved": False,
            "investment_decision_allowed": False,
            "realized_savings_proven": False,
        }

    return {
        "candidate_economics_version": CANDIDATE_ECONOMICS_VERSION,
        "available": bool(economics.get("available")),
        "preview_only": True,
        "layout_fingerprint": replay.get("layout_fingerprint"),
        "candidate_label": candidate_label,
        "baseline_candidate_summary": deepcopy(baseline),
        "candidate_summary": deepcopy(candidate),
        "economics": economics,
        "production_evidence": False,
        "finance_approved": False,
        "investment_decision_allowed": False,
        "realized_savings_proven": False,
        "auto_execute_allowed": False,
        "evidence_boundary": (
            "economics are tied to a fingerprint-replayed V5 candidate and sourced "
            "assumptions; realized value still requires installation, post-change KPI "
            "measurement and finance validation"
        ),
    }
